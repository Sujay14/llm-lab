"""TriageLens web server (FastAPI).  Run with:  python run.py"""
import csv
import difflib
import io
import json
import os
import re
import shutil
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import triage

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
RULES_PATH = os.path.join(db.DATA_DIR, "rules.json")
if not os.path.exists(RULES_PATH):  # first run: copy the default rules so they can be edited in the UI
    shutil.copy(os.path.join(HERE, "rules.json"), RULES_PATH)

DEFAULT_CHECKERS = ["Me", "Checker A", "Checker B"]

app = FastAPI(title="TriageLens")


# ---------------------------------------------------------------- models ----
class SubmissionIn(BaseModel):
    title: str
    abstract: str = ""
    tags: List[str] = []
    external_id: str = ""


class SubmissionPatch(BaseModel):
    title: Optional[str] = None
    abstract: Optional[str] = None
    tags: Optional[List[str]] = None
    specialty_override: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    checks_done: Optional[List[str]] = None


class TextIn(BaseModel):
    text: str


class SettingsIn(BaseModel):
    model: Optional[str] = None
    checkers: Optional[List[str]] = None


# --------------------------------------------------------------- helpers ----
def norm(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def find_duplicate(title):
    t = norm(title)
    for s in db.list_all():
        if difflib.SequenceMatcher(None, t, norm(s["title"])).ratio() >= 0.88:
            return s["id"]
    return None


def create(title, abstract="", tags=None, external_id=""):
    title = title.strip()
    if not title:
        raise HTTPException(400, "Title is required")
    return db.add(title, abstract.strip(), tags or [], external_id.strip(), find_duplicate(title))


def split_tags(value):
    return [t.strip() for t in re.split(r"[;,|]", value or "") if t.strip()]


def rules():
    return triage.load_rules(RULES_PATH)


# ------------------------------------------------------------------ API ----
@app.get("/api/status")
def status():
    models = triage.ollama_models()
    return {
        "ollama": models is not None,
        "models": models or [],
        "model": db.get_setting("model", triage.DEFAULT_MODEL),
        "url": triage.OLLAMA_URL,
    }


@app.get("/api/settings")
def get_settings():
    return {
        "model": db.get_setting("model", triage.DEFAULT_MODEL),
        "checkers": db.get_setting("checkers", DEFAULT_CHECKERS),
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    if body.model is not None:
        db.set_setting("model", body.model.strip() or triage.DEFAULT_MODEL)
    if body.checkers is not None:
        names = [c.strip() for c in body.checkers if c.strip()]
        db.set_setting("checkers", names or DEFAULT_CHECKERS)
    return get_settings()


@app.get("/api/rules")
def get_rules():
    return rules()


@app.put("/api/rules")
def put_rules(new_rules: dict):
    try:
        triage.validate_rules(new_rules)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(new_rules, f, indent=2, ensure_ascii=False)
    return new_rules


@app.get("/api/submissions")
def list_submissions():
    return db.list_all()


@app.post("/api/submissions")
def add_submission(body: SubmissionIn):
    return create(body.title, body.abstract, body.tags, body.external_id)


@app.post("/api/import/titles")
def import_titles(body: TextIn):
    lines = [ln.strip() for ln in body.text.splitlines() if ln.strip()]
    made = [create(t) for t in lines]
    return {"added": len(made)}


@app.post("/api/import/csv")
def import_csv(body: TextIn):
    reader = csv.DictReader(io.StringIO(body.text.lstrip("﻿")))
    count = 0
    for raw in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if r.get("title"):
            create(r["title"], r.get("abstract", ""), split_tags(r.get("tags", "")), r.get("id", ""))
            count += 1
    if not count:
        raise HTTPException(400, "No rows found. The CSV needs a header with at least a 'title' column.")
    return {"added": count}


@app.post("/api/demo")
def load_demo():
    existing = {norm(s["title"]) for s in db.list_all()}
    count = 0
    with open(os.path.join(HERE, "sample_input.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if norm(r["title"]) not in existing:
                create(r["title"], r.get("abstract", ""), split_tags(r.get("tags", "")), r.get("id", ""))
                count += 1
    return {"added": count}


@app.patch("/api/submissions/{sub_id}")
def patch_submission(sub_id: int, body: SubmissionPatch):
    if not db.get(sub_id):
        raise HTTPException(404, "Not found")
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] not in db.STATUSES:
        raise HTTPException(400, "Invalid status")
    return db.update(sub_id, fields)


@app.delete("/api/submissions/{sub_id}")
def delete_submission(sub_id: int):
    db.delete(sub_id)
    return {"ok": True}


@app.post("/api/submissions/{sub_id}/analyze")
def analyze(sub_id: int):
    sub = db.get(sub_id)
    if not sub:
        raise HTTPException(404, "Not found")
    model = db.get_setting("model", triage.DEFAULT_MODEL)
    result = triage.analyse(rules(), sub, model=model)
    return db.save_analysis(sub_id, result)


@app.get("/api/export.csv")
def export_csv():
    labels = {k: v["label"] for k, v in rules()["checks"].items()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "status", "category", "study_type", "specialty", "assigned_to",
                "checks_required", "checks_done", "confidence", "attention_points", "notes", "source"])
    for s in reversed(db.list_all()):
        a = s["analysis"] or {}
        w.writerow([
            s["external_id"] or s["id"], s["title"], s["status"], a.get("category", ""), a.get("study_type", ""),
            s["specialty_override"] or a.get("suggested_specialty", ""), s["assigned_to"],
            "; ".join(labels.get(c, c) for c in a.get("checks_required", [])),
            "; ".join(labels.get(c, c) for c in s["checks_done"]),
            "" if a.get("confidence") is None else a.get("confidence"),
            " | ".join(a.get("attention_points", [])), s["notes"], a.get("source", ""),
        ])
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=triage_export.csv"},
    )


# ---------------------------------------------------------------- static ----
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
