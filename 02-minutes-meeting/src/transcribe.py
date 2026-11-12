"""Speech-to-text with faster-whisper (open source, local, CPU friendly).

faster-whisper bundles its own audio decoder, so no separate FFmpeg install is
needed on Windows. The model is downloaded once on first use, then cached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

_MODELS: dict = {}


@dataclass
class Transcript:
    text: str
    segments: list = field(default_factory=list)  # [{"start", "end", "text"}]
    language: str = ""
    duration: float = 0.0


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


def format_transcript(segments: list, with_timestamps: bool = True) -> str:
    lines = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        speaker = str(seg.get("speaker", "")).strip()
        prefix = f"{speaker}: " if speaker else ""
        if with_timestamps:
            lines.append(f"[{format_timestamp(seg['start'])}] {prefix}{text}")
        else:
            lines.append(f"{prefix}{text}")
    return "\n".join(lines)


def _load_model(size: str):
    if size not in _MODELS:
        from faster_whisper import WhisperModel  # imported lazily: heavy

        _MODELS[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODELS[size]


def transcribe_file(
    path: str,
    model_size: str = "base",
    language: Optional[str] = None,
    progress: Optional[Callable[[float, str], None]] = None,
    initial_prompt: Optional[str] = None,
) -> Transcript:
    """Transcribe an audio/video file. `progress(fraction, message)` is optional."""
    if progress:
        progress(0.0, f"Loading Whisper '{model_size}' model (first run downloads it)…")
    model = _load_model(model_size)

    seg_iter, info = model.transcribe(
        path, language=language, beam_size=3, vad_filter=True,
        initial_prompt=initial_prompt or None,
    )
    total = float(getattr(info, "duration", 0.0) or 0.0)

    segments = []
    for seg in seg_iter:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        if progress and total > 0:
            progress(min(seg.end / total, 1.0), f"Transcribing… {format_timestamp(seg.end)} / {format_timestamp(total)}")

    text = " ".join(s["text"] for s in segments).strip()
    return Transcript(
        text=text,
        segments=segments,
        language=getattr(info, "language", "") or "",
        duration=total,
    )
