"""Turn a transcript into structured meeting minutes with Llama 3.2 via Ollama."""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from . import config


class OllamaUnavailable(RuntimeError):
    """Ollama is not running, or the model is not pulled."""


SYSTEM_PROMPT = (
    "You are a meticulous executive assistant who writes professional meeting minutes. "
    "Use ONLY information stated in the transcript. Never invent names, dates, numbers or "
    "decisions. If something is not stated, leave it empty. Write in a formal, neutral, "
    "concise business tone. Respond with a single JSON object and nothing else."
)

SCHEMA_HINT = """Return JSON with exactly these keys:
{
  "title": "short descriptive meeting title",
  "executive_summary": "2-4 sentence overview of the meeting",
  "participants": ["names or roles mentioned as taking part"],
  "discussion_points": [{"topic": "short heading", "detail": "what was said", "timestamp": "timestamp from transcript or empty"}],
  "decisions": ["each decision that was made"],
  "action_items": [{"task": "what must be done", "owner": "person responsible or empty", "deadline": "due date as stated or empty"}],
  "open_questions": ["unresolved questions or risks"]
}"""

EMPTY_MINUTES = {
    "title": "",
    "executive_summary": "",
    "participants": [],
    "discussion_points": [],
    "decisions": [],
    "action_items": [],
    "open_questions": [],
}


# --------------------------------------------------------------------------- #
# Pure helpers (unit tested)
# --------------------------------------------------------------------------- #
def split_text(text: str, max_chars: int = config.CHUNK_CHARS) -> list[str]:
    """Split a long transcript into chunks on line/sentence boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    units: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= max_chars:
            units.append(line)
            continue
        for sent in re.split(r"(?<=[.!?])\s+", line):
            while len(sent) > max_chars:
                units.append(sent[:max_chars])
                sent = sent[max_chars:]
            if sent:
                units.append(sent)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) + 1 > max_chars:
            chunks.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
    if current:
        chunks.append(current)
    return chunks


def parse_json(raw: str) -> Optional[dict]:
    """Extract a JSON object from model output, tolerating code fences and chatter."""
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _str_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict):
            item = " — ".join(_s(v) for v in item.values() if _s(v))
        item = _s(item)
        if item:
            out.append(item)
    return out


def normalize_minutes(data: Optional[dict]) -> dict:
    """Coerce whatever the model returned into the expected shape."""
    data = data or {}
    result = {k: (list(v) if isinstance(v, list) else v) for k, v in EMPTY_MINUTES.items()}
    result["title"] = _s(data.get("title"))
    result["executive_summary"] = _s(data.get("executive_summary") or data.get("summary"))
    result["participants"] = _str_list(data.get("participants"))
    result["decisions"] = _str_list(data.get("decisions"))
    result["open_questions"] = _str_list(data.get("open_questions"))

    points = []
    for item in data.get("discussion_points") or []:
        if isinstance(item, dict):
            topic, detail = _s(item.get("topic")), _s(item.get("detail"))
            timestamp = _s(item.get("timestamp") or item.get("time"))
        else:
            topic, detail, timestamp = "", _s(item), ""
        if topic or detail:
            points.append({"topic": topic, "detail": detail, "timestamp": timestamp})
    result["discussion_points"] = points

    actions = []
    for item in data.get("action_items") or []:
        if isinstance(item, dict):
            task = _s(item.get("task") or item.get("action"))
            owner = _s(item.get("owner") or item.get("assignee"))
            deadline = _s(item.get("deadline") or item.get("due"))
        else:
            task, owner, deadline = _s(item), "", ""
        if task:
            actions.append({"task": task, "owner": owner, "deadline": deadline})
    result["action_items"] = actions
    return result


def _dedupe(items: list, key) -> list:
    seen, out = set(), []
    for item in items:
        k = key(item).lower()
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return out


def merge_minutes(parts: list[dict]) -> dict:
    """Combine per-chunk results into one set of minutes (summary added later)."""
    merged = normalize_minutes(None)
    for part in parts:
        merged["participants"] += part["participants"]
        merged["discussion_points"] += part["discussion_points"]
        merged["decisions"] += part["decisions"]
        merged["action_items"] += part["action_items"]
        merged["open_questions"] += part["open_questions"]
    merged["participants"] = _dedupe(merged["participants"], lambda x: x)
    merged["decisions"] = _dedupe(merged["decisions"], lambda x: x)
    merged["open_questions"] = _dedupe(merged["open_questions"], lambda x: x)
    merged["discussion_points"] = _dedupe(
        merged["discussion_points"], lambda x: x["topic"] + x["detail"][:60]
    )
    merged["action_items"] = _dedupe(merged["action_items"], lambda x: x["task"])
    return merged


# --------------------------------------------------------------------------- #
# Ollama access
# --------------------------------------------------------------------------- #
def _client(host: str):
    import ollama  # imported lazily so tests run without it

    return ollama.Client(host=host)


def _model_names(listing) -> list[str]:
    models = listing["models"] if isinstance(listing, dict) else getattr(listing, "models", [])
    names = []
    for m in models:
        name = m.get("model") or m.get("name") if isinstance(m, dict) else (
            getattr(m, "model", None) or getattr(m, "name", None)
        )
        if name:
            names.append(name)
    return names


def check_ollama(host: str = config.OLLAMA_HOST, model: str = config.OLLAMA_MODEL) -> tuple[str, str]:
    """Return (status, message) where status is 'ok', 'no_server' or 'no_model'."""
    try:
        names = _model_names(_client(host).list())
    except Exception:
        return "no_server", "Ollama is not running. Start the Ollama app and refresh."
    wanted = model if ":" in model else f"{model}:latest"
    if not any(n == model or n == wanted or n.split(":")[0] == model for n in names):
        return "no_model", f"Model not found. Run:  ollama pull {model}"
    return "ok", f"Ollama is ready · {model}"


def _chat(host: str, model: str, system: str, user: str) -> str:
    try:
        response = _client(host).chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            format="json",
            options={
                "temperature": config.OLLAMA_TEMPERATURE,
                "num_ctx": config.OLLAMA_NUM_CTX,
            },
        )
    except Exception as exc:
        raise OllamaUnavailable(
            f"Could not get an answer from Ollama ({exc}). "
            f"Make sure Ollama is running and '{model}' is pulled."
        ) from exc
    message = response["message"] if isinstance(response, dict) else response.message
    return message["content"] if isinstance(message, dict) else message.content


def _ask_for_json(host: str, model: str, system: str, user: str) -> dict:
    """Ask once; retry once with a firmer reminder if the JSON is unusable."""
    data = parse_json(_chat(host, model, system, user))
    if data is None:
        data = parse_json(_chat(host, model, system, user + "\n\nReturn ONLY valid JSON."))
    if data is None:
        raise RuntimeError("The model did not return valid JSON. Please try again.")
    return data


def _extract_prompt(chunk: str, detail: str, attendees: str, part: Optional[tuple[int, int]], summary_style: str = "Professional") -> str:
    style_guidance = {
        "Professional": "Use polished, formal business language.",
        "Short & concise": "Keep the executive summary very short and retain only critical notes.",
        "Story-oriented": "Write the executive summary as a clear narrative showing how the discussion progressed.",
        "Action-focused": "Prioritize outcomes, decisions, owners and next steps in the summary.",
    }.get(summary_style, "Use polished, formal business language.")
    lines = [SCHEMA_HINT, "", style_guidance, config.DETAIL_LEVELS.get(detail, config.DETAIL_LEVELS["Standard"])]
    if attendees.strip():
        lines.append(f"Known attendees (use these spellings): {attendees.strip()}")
    if part:
        lines.append(
            f"This is part {part[0]} of {part[1]} of a longer meeting; extract only what appears in this part."
        )
    lines += ["", "TRANSCRIPT:", chunk]
    return "\n".join(lines)


def generate_minutes(
    transcript: str,
    *,
    model: str = config.OLLAMA_MODEL,
    host: str = config.OLLAMA_HOST,
    detail: str = "Standard",
    attendees: str = "",
    progress: Optional[Callable[[float, str], None]] = None,
    summary_style: str = "Professional",
) -> dict:
    """Return normalized minutes for a transcript of any length."""
    transcript = (transcript or "").strip()
    if len(transcript) < 20:
        raise ValueError("The transcript is too short to summarise.")

    chunks = split_text(transcript)
    total = len(chunks)

    if total == 1:
        if progress:
            progress(0.1, "Drafting the minutes…")
        data = _ask_for_json(host, model, SYSTEM_PROMPT, _extract_prompt(chunks[0], detail, attendees, None, summary_style))
        if progress:
            progress(1.0, "Minutes ready.")
        return normalize_minutes(data)

    parts = []
    for i, chunk in enumerate(chunks, start=1):
        if progress:
            progress((i - 1) / (total + 1), f"Reading part {i} of {total}…")
        data = _ask_for_json(host, model, SYSTEM_PROMPT, _extract_prompt(chunk, detail, attendees, (i, total), summary_style))
        parts.append(normalize_minutes(data))

    merged = merge_minutes(parts)

    if progress:
        progress(total / (total + 1), "Writing the executive summary…")
    digest = json.dumps(
        {
            "discussion_points": merged["discussion_points"],
            "decisions": merged["decisions"],
            "action_items": merged["action_items"],
        },
        ensure_ascii=False,
    )
    final = _ask_for_json(
        host,
        model,
        SYSTEM_PROMPT,
        'Based on these extracted notes from one meeting, return JSON with exactly two keys: '
        '"title" (short descriptive meeting title) and "executive_summary" (2-4 sentences).\n\n'
        f"NOTES:\n{digest}",
    )
    merged["title"] = _s(final.get("title"))
    merged["executive_summary"] = _s(final.get("executive_summary") or final.get("summary"))
    if progress:
        progress(1.0, "Minutes ready.")
    return merged
