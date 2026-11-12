"""Core triage logic: rule checks + local Llama (Ollama) analysis.

Everything here is UI-agnostic so the web server and any script can share it.
"""
import json
import os
import re

try:
    import requests
except ImportError:  # only needed for LLM mode
    requests = None

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
CATEGORIES = ["clinical", "biomedical_computational", "preclinical_lab", "non_medical"]


# ---------------------------------------------------------------- rules ----
def load_rules(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_rules(rules):
    """Raise ValueError with a readable message if the rules JSON is malformed."""
    if not isinstance(rules, dict):
        raise ValueError("Rules must be a JSON object")
    if not isinstance(rules.get("default_specialty"), str) or not rules["default_specialty"].strip():
        raise ValueError('"default_specialty" must be a non-empty string')
    specs = rules.get("specialties")
    if not isinstance(specs, dict) or not specs:
        raise ValueError('"specialties" must be an object of {name: [keywords]}')
    for name, words in specs.items():
        if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
            raise ValueError(f'Specialty "{name}" needs a list of keyword strings')
    checks = rules.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError('"checks" must be an object of {key: {label, triggers}}')
    for key, spec in checks.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("label"), str):
            raise ValueError(f'Check "{key}" needs a "label" string')
        trig = spec.get("triggers")
        if not isinstance(trig, list) or not all(isinstance(t, str) for t in trig):
            raise ValueError(f'Check "{key}" needs a "triggers" list of regex strings')
        for t in trig:
            try:
                re.compile(t)
            except re.error as e:
                raise ValueError(f'Check "{key}": bad regex "{t}" ({e})')
    return rules


# ---------------------------------------------------------- rule-based -----
def _text(row, with_abstract=True):
    parts = [row.get("title", ""), " ".join(row.get("tags", []))]
    if with_abstract:
        parts.append(row.get("abstract", ""))
    return " ".join(parts).lower()


def rule_checks(rules, row):
    text = _text(row)
    hits = [k for k, spec in rules["checks"].items() if any(re.search(p, text) for p in spec["triggers"])]
    # Reviews / meta-analyses reuse published data: no new consent or ethics approval needed.
    if "prisma" in hits and "ethics_human" in hits:
        hits.remove("ethics_human")
    return hits


def rule_specialty(rules, row):
    """Title matches weigh 3, tag and abstract matches weigh 1."""
    title = row.get("title", "").lower()
    rest = (" ".join(row.get("tags", [])) + " " + row.get("abstract", "")).lower()
    best, best_score = rules["default_specialty"], 0
    for name, words in rules["specialties"].items():
        score = sum(3 for w in words if w.lower() in title) + sum(1 for w in words if w.lower() in rest)
        if score > best_score:
            best, best_score = name, score
    return best


def rule_category(row, hits):
    text = _text(row)
    if "ethics_human" in hits or re.search(r"patient|clinical|cohort|trial|meta-analysis|systematic review", text):
        return "clinical"
    if re.search(r"bioinformatic|network pharmacology|docking|deep learning|in silico|machine learning", text):
        return "biomedical_computational"
    if re.search(r"\bmice\b|\bmouse\b|\brats?\b|cell line|in vitro|in vivo", text):
        return "preclinical_lab"
    return "non_medical"


def rules_only(rules, row):
    hits = rule_checks(rules, row)
    return {
        "category": rule_category(row, hits),
        "study_type": "",
        "summary": "",
        "checks_required": hits,
        "suggested_specialty": rule_specialty(rules, row),
        "attention_points": [],
        "confidence": None,
        "reason": "Rule-based result (Llama not used).",
        "source": "rules",
    }


# ------------------------------------------------------------------ LLM ----
def ollama_models(url=None):
    """Return list of installed model names, or None if Ollama is unreachable."""
    if requests is None:
        return None
    try:
        r = requests.get(f"{(url or OLLAMA_URL)}/api/tags", timeout=2)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except Exception:
        return None


def build_prompt(rules, row):
    checks = "\n".join(f'- "{k}": {v["label"]}' for k, v in rules["checks"].items())
    specs = ", ".join(f'"{s}"' for s in list(rules["specialties"]) + [rules["default_specialty"]])
    return f"""You are an assistant for editorial staff who triage newly submitted biomedical manuscripts.
Read the submission and answer ONLY with one JSON object.

Submission
Title: {row['title']}
Subject tags: {', '.join(row.get('tags', [])) or 'none given'}
Abstract: {row.get('abstract') or 'not provided (judge from the title only and lower your confidence)'}

Return JSON with exactly these keys:
- "category": one of {json.dumps(CATEGORIES)}
- "study_type": short phrase, e.g. "systematic review and meta-analysis", "in-silico drug mechanism study"
- "summary": one plain-language sentence saying what the study did
- "checks_required": list using ONLY these keys:
{checks}
- "suggested_specialty": exactly one of [{specs}]
- "attention_points": up to 3 short points an editor should double-check (scope fit, overclaiming, missing validation, unclear data source). Empty list if none.
- "confidence": number from 0 to 1
- "reason": one short sentence explaining the specialty and checks you chose

Do not invent details that are not in the submission."""


def ask_llm(model, prompt, url=None, timeout=240):
    resp = requests.post(
        f"{(url or OLLAMA_URL)}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def clean_llm(rules, data):
    """Force model output into the allowed vocabulary."""
    valid_specs = list(rules["specialties"]) + [rules["default_specialty"]]
    checks = data.get("checks_required") or []
    if isinstance(checks, str):
        checks = [checks]
    points = data.get("attention_points") or []
    if isinstance(points, str):
        points = [points]
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence"))))
    except (TypeError, ValueError):
        conf = None
    return {
        "category": data.get("category") if data.get("category") in CATEGORIES else "",
        "study_type": str(data.get("study_type", ""))[:120],
        "summary": str(data.get("summary", ""))[:300],
        "checks_required": [c for c in checks if c in rules["checks"]],
        "suggested_specialty": data.get("suggested_specialty") if data.get("suggested_specialty") in valid_specs else "",
        "attention_points": [str(p)[:200] for p in points[:3]],
        "confidence": conf,
        "reason": str(data.get("reason", ""))[:300],
    }


def analyse(rules, row, model=None, url=None, use_llm=True):
    base = rules_only(rules, row)
    if not use_llm or requests is None:
        return base
    try:
        llm = clean_llm(rules, ask_llm(model or DEFAULT_MODEL, build_prompt(rules, row), url))
    except Exception as e:
        base["reason"] = f"Llama call failed ({type(e).__name__}); rule-based result shown instead."
        return base
    # Rule triggers are always kept: the LLM can add checks but never remove one.
    merged = [k for k in rules["checks"] if k in set(llm["checks_required"]) | set(base["checks_required"])]
    return {
        "category": llm["category"] or base["category"],
        "study_type": llm["study_type"],
        "summary": llm["summary"],
        "checks_required": merged,
        "suggested_specialty": llm["suggested_specialty"] or base["suggested_specialty"],
        "attention_points": llm["attention_points"],
        "confidence": llm["confidence"],
        "reason": llm["reason"],
        "source": "llama",
    }
