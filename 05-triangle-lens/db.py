"""SQLite storage for the queue and settings."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "triage.db")

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_id TEXT DEFAULT '',
        title TEXT NOT NULL,
        abstract TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        analysis TEXT,
        analyzed_at TEXT,
        specialty_override TEXT DEFAULT '',
        assigned_to TEXT DEFAULT '',
        status TEXT DEFAULT 'new',
        notes TEXT DEFAULT '',
        checks_done TEXT DEFAULT '[]',
        dup_of INTEGER
    );
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    """
)
_conn.commit()

STATUSES = ("new", "analyzed", "assigned", "done")
EDITABLE = {"title", "abstract", "tags", "specialty_override", "assigned_to", "status", "notes", "checks_done"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r):
    d = dict(r)
    d["tags"] = json.loads(d["tags"] or "[]")
    d["checks_done"] = json.loads(d["checks_done"] or "[]")
    d["analysis"] = json.loads(d["analysis"]) if d["analysis"] else None
    return d


def list_all():
    with _lock:
        return [_row(r) for r in _conn.execute("SELECT * FROM submissions ORDER BY id DESC")]


def get(sub_id):
    with _lock:
        r = _conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    return _row(r) if r else None


def add(title, abstract="", tags=None, external_id="", dup_of=None):
    with _lock:
        cur = _conn.execute(
            "INSERT INTO submissions (external_id,title,abstract,tags,created_at,dup_of) VALUES (?,?,?,?,?,?)",
            (external_id, title, abstract, json.dumps(tags or []), _now(), dup_of),
        )
        _conn.commit()
        new_id = cur.lastrowid
    return get(new_id)


def update(sub_id, fields):
    cols, vals = [], []
    for k, v in fields.items():
        if k not in EDITABLE:
            continue
        if k in ("tags", "checks_done"):
            v = json.dumps(v)
        cols.append(f"{k}=?")
        vals.append(v)
    if cols:
        with _lock:
            _conn.execute(f"UPDATE submissions SET {', '.join(cols)} WHERE id=?", (*vals, sub_id))
            _conn.commit()
    return get(sub_id)


def save_analysis(sub_id, analysis):
    sub = get(sub_id)
    if not sub:
        return None
    status = "analyzed" if sub["status"] == "new" else sub["status"]
    keep = [c for c in sub["checks_done"] if c in analysis["checks_required"]]
    with _lock:
        _conn.execute(
            "UPDATE submissions SET analysis=?, analyzed_at=?, status=?, checks_done=? WHERE id=?",
            (json.dumps(analysis), _now(), status, json.dumps(keep), sub_id),
        )
        _conn.commit()
    return get(sub_id)


def delete(sub_id):
    with _lock:
        _conn.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
        _conn.commit()


def get_setting(key, default=None):
    with _lock:
        r = _conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(key, value):
    with _lock:
        _conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, json.dumps(value)))
        _conn.commit()
