"""Local model stages, each run in its own process so memory is released between stages.

python -m rec.models diarize <wav> <out.json>   Nemotron 3 Diarization → [{start,end,speaker}]
python -m rec.models asr <wav> <out.json>       Qwen3-ASR (60 s chunks) + ForcedAligner → [{start,end,text}] words
python -m rec.models alt <wav> <out.json>       Whisper large-v3-turbo → [{start,end,text}] words
python -m rec.models prefetch                   download every model once (the pipeline runs offline)
Model ids and chunking come from rec.config (validated in docs/benchmark.md).
"""
import json
import sys
from pathlib import Path

from . import config


def diarize(wav: str):
    import mlx.core as mx
    import soundfile as sf
    from mlx_audio.vad import load

    audio, sr = sf.read(wav, dtype="float32")
    r = load(config.DIAR_MODEL).generate(mx.array(audio), sample_rate=sr)
    return [{"start": float(s.start), "end": float(s.end), "speaker": str(s.speaker)} for s in r.segments]


def asr(wav: str):
    import numpy as np
    import soundfile as sf
    from mlx_audio.stt import load

    audio, sr = sf.read(wav, dtype="float32")
    # max_tokens is a budget for the whole recording, not per chunk (default 8192 silently truncates ~40 min).
    r = load(config.ASR_MODEL).generate(wav, language="Korean", chunk_duration=config.ASR_CHUNK_SEC,
                                         max_tokens=200000)
    aligner = load(config.ALIGNER_MODEL)
    words = []
    for s in r.segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        st, en = float(s["start"]), float(s["end"])
        piece = np.ascontiguousarray(audio[int(st * sr):int(en * sr)])
        for w in aligner.generate(audio=piece, text=text, language="Korean"):
            words.append({"start": st + w.start_time, "end": st + w.end_time, "text": w.text})
    return words


def alt(wav: str):
    import mlx_whisper

    r = mlx_whisper.transcribe(wav, path_or_hf_repo=config.ALT_ASR_MODEL, language="ko",
                               word_timestamps=True, condition_on_previous_text=False)
    return [{"start": w["start"], "end": w["end"], "text": w["word"]}
            for s in r["segments"] for w in s.get("words", [])]


STAGES = {"diarize": diarize, "asr": asr, "alt": alt}


def prefetch() -> None:
    import os

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # Xet downloads stalled at 0 bytes on macOS
    from huggingface_hub import snapshot_download

    for repo in (config.DIAR_MODEL, config.ASR_MODEL, config.ALIGNER_MODEL, config.ALT_ASR_MODEL):
        print("fetching", repo, flush=True)
        snapshot_download(repo)


def main():
    if sys.argv[1:] == ["prefetch"]:
        prefetch()
        return
    stage, wav, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    result = STAGES[stage](wav)
    tmp = out.with_suffix(".part")
    tmp.write_text(json.dumps(result, ensure_ascii=False))
    tmp.rename(out)


if __name__ == "__main__":
    main()
