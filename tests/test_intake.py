import os
import shutil
import unicodedata
import subprocess

import pytest
from pathlib import Path

from rec import config, db, intake


def tone(path, seconds):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:a", "aac", str(path)], check=True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("INBOX", "ARCHIVE"):
        (tmp_path / name).mkdir()
        monkeypatch.setattr(config, name, tmp_path / name)
    monkeypatch.setattr(config, "MIN_DURATION_SEC", 2)
    monkeypatch.setattr(config, "STABLE_SEC", 60)
    con = db.connect(tmp_path / "state.sqlite3")
    return tmp_path, con


def jobs(con):
    return {r["source_name"]: (r["status"], r["error"]) for r in con.execute("SELECT * FROM jobs")}


def test_waits_until_stable_then_enqueues_once(env):
    tmp, con = env
    f = tmp / "INBOX" / "음성 261109_101500.m4a"
    tone(f, 3)
    os.utime(f, (1000, 1000))
    assert intake.scan(con, now=1010) == []          # first sighting: not yet stable
    assert len(intake.scan(con, now=1100)) == 1      # unchanged for 60 s → queued
    assert intake.scan(con, now=1200) == []          # never twice
    (status, _), = jobs(con).values()
    assert status == "queued"
    job = con.execute("SELECT * FROM jobs").fetchone()
    assert job["job_id"].startswith("20261109-101500-")
    assert intake.sha256(f) == intake.sha256(Path(job["archive_path"]))


def test_growing_file_is_not_taken(env):
    tmp, con = env
    f = tmp / "INBOX" / "a.m4a"
    tone(f, 3)
    os.utime(f, (1000, 1000))
    intake.scan(con, now=1010)
    with f.open("ab") as h:
        h.write(b"\0" * 10)                          # still being written by Syncthing
    os.utime(f, (1065, 1065))
    assert intake.scan(con, now=1070) == []
    assert intake.scan(con, now=1200) != []


def test_same_audio_under_another_name_is_ignored(env):
    tmp, con = env
    a = tmp / "INBOX" / "a.m4a"
    tone(a, 3)
    shutil.copy(a, tmp / "INBOX" / "a (1).m4a")
    for p in (tmp / "INBOX").iterdir():
        os.utime(p, (1000, 1000))
    intake.scan(con, now=1010)
    intake.scan(con, now=1100)
    assert len(jobs(con)) == 1


def test_rejects_short_undecodable_calls_symlinks_and_other_types(env):
    tmp, con = env
    inbox = tmp / "INBOX"
    tone(inbox / "short.m4a", 1)
    (inbox / "broken.m4a").write_bytes(b"not audio at all" * 100)
    tone(inbox / "통화 홍길동_261109.m4a", 3)
    tone(tmp / "outside.m4a", 3)
    (inbox / "link.m4a").symlink_to(tmp / "outside.m4a")
    (inbox / "notes.txt").write_text("x")
    shutil.copy(inbox / "short.m4a", inbox / "clip.mp3")
    for p in inbox.iterdir():
        if not p.is_symlink():
            os.utime(p, (1000, 1000))
    intake.scan(con, now=1010)
    intake.scan(con, now=1100)
    assert jobs(con) == {"short.m4a": ("skipped", "too_short"), "broken.m4a": ("skipped", "decode")}
    assert not any((tmp / "ARCHIVE").iterdir())     # skipped files are not archived


def test_recordings_from_before_the_cutoff_are_skipped(env, monkeypatch):
    tmp, con = env
    from datetime import datetime
    monkeypatch.setattr(config, "SINCE", datetime(2026, 11, 9, 10, 59))
    for name, secs in (("음성 261109_105834.m4a", 3), ("음성 261109_110500.m4a", 4)):  # different audio → different hash
        tone(tmp / "INBOX" / name, secs)
        os.utime(tmp / "INBOX" / name, (1000, 1000))
    intake.scan(con, now=1010)
    intake.scan(con, now=1100)
    assert jobs(con) == {"음성 261109_105834.m4a": ("skipped", "before_cutoff"), "음성 261109_110500.m4a": ("queued", None)}


def test_backfilled_recordings_bypass_the_cutoff(env, monkeypatch):
    tmp, con = env
    from datetime import datetime
    monkeypatch.setattr(config, "SINCE", datetime(2026, 11, 9, 10, 59))
    monkeypatch.setattr(config, "INCLUDE", tmp / "include.txt")
    (tmp / "include.txt").write_text("음성 261106_142617.m4a\n", encoding="utf-8")
    for name, secs in (("음성 261106_142617.m4a", 3), ("음성 261105_083634.m4a", 4)):
        name = unicodedata.normalize("NFD", name)  # how Syncthing on macOS stores Korean names
        tone(tmp / "INBOX" / name, secs)
        os.utime(tmp / "INBOX" / name, (1000, 1000))
    intake.scan(con, now=1010)
    intake.scan(con, now=1100)
    assert {unicodedata.normalize("NFC", k): v for k, v in jobs(con).items()} == {
        "음성 261106_142617.m4a": ("queued", None), "음성 261105_083634.m4a": ("skipped", "before_cutoff")}
