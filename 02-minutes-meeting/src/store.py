"""Local JSON meeting library. Audio is only copied when explicitly requested."""
from __future__ import annotations
import json, re, shutil
from datetime import datetime, timezone
from pathlib import Path
from .config import ROOT

LIBRARY_DIR = ROOT / "meetings"
AUDIO_DIR = LIBRARY_DIR / "audio"

def _safe_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return value[:70] or "meeting"

def save_meeting(record: dict, audio_path: str | None = None, keep_audio: bool = False) -> Path:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("id", datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    record.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    record["id"] = _safe_id(str(record["id"]))
    if keep_audio and audio_path:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        source = Path(audio_path)
        target = AUDIO_DIR / f"{record['id']}{source.suffix.lower()}"
        shutil.copy2(source, target)
        record["audio_file"] = str(target.relative_to(ROOT))
    path = LIBRARY_DIR / f"{record['id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def list_meetings() -> list[dict]:
    if not LIBRARY_DIR.exists(): return []
    records = []
    for path in sorted(LIBRARY_DIR.glob("*.json"), reverse=True):
        try: records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError): continue
    return records

def load_meeting(meeting_id: str) -> dict | None:
    path = LIBRARY_DIR / f"{_safe_id(meeting_id)}.json"
    if not path.exists(): return None
    return json.loads(path.read_text(encoding="utf-8"))

def delete_meeting(meeting_id: str) -> bool:
    path = LIBRARY_DIR / f"{_safe_id(meeting_id)}.json"
    if not path.exists(): return False
    record = load_meeting(meeting_id) or {}
    audio = record.get("audio_file")
    if audio:
        target = ROOT / audio
        if target.exists() and target.is_file() and AUDIO_DIR in target.parents: target.unlink()
    path.unlink()
    return True
