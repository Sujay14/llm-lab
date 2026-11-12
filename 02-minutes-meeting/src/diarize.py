"""Optional pyannote speaker diarization. Requires user-supplied HF access token."""
from __future__ import annotations

def diarize_file(audio_path: str, hf_token: str):
    if not hf_token or not hf_token.strip():
        raise ValueError("A Hugging Face access token is required for optional diarization.")
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError("Install optional diarization dependencies: pip install pyannote.audio") from exc
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
        annotation = pipeline(audio_path)
    except Exception as exc:
        raise RuntimeError(f"Speaker diarization failed: {exc}") from exc
    rows = []
    for segment, _, speaker in annotation.itertracks(yield_label=True):
        rows.append({"start": float(segment.start), "end": float(segment.end), "speaker": str(speaker)})
    return rows

def assign_speakers(segments: list[dict], diarization: list[dict]) -> list[dict]:
    """Assign each Whisper segment the speaker with greatest temporal overlap."""
    output = []
    for seg in segments:
        best, overlap = "Unknown", 0.0
        for turn in diarization:
            amount = max(0.0, min(seg["end"], turn["end"]) - max(seg["start"], turn["start"]))
            if amount > overlap: best, overlap = turn["speaker"], amount
        output.append({**seg, "speaker": best})
    return output
