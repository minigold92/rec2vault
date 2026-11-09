"""script.md -> 음성 261110_100000.m4a (macOS `say` Korean voices + ffmpeg). Run on a Mac with the voices installed."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "음성 261110_100000.m4a"
VOICES = {"한다온": "Yuna (한국어(한국))", "오지안": "Eddy (한국어(한국))", "문태오": "Shelley (한국어(한국))"}
GAP_SEC = 0.7

lines = [m.groups() for m in re.finditer(r"^\d+\. \*\*(.+?)\*\*: (.+)$", (HERE / "script.md").read_text(encoding="utf-8"), re.M)]
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(GAP_SEC),
                    "-c:a", "pcm_s16le", str(tmp / "gap.wav")], check=True)
    parts = []
    for i, (who, text) in enumerate(lines):
        aiff, wav = tmp / f"{i:02d}.aiff", tmp / f"{i:02d}.wav"
        subprocess.run(["say", "-v", VOICES[who], "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(aiff), "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)], check=True)
        parts += [wav, tmp / "gap.wav"]
    (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "1", str(OUT)], check=True)
print(OUT, len(lines), "utterances", file=sys.stderr)
