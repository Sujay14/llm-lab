"""Optional LLM explainers: Ollama (local, e.g. llama3.2-vision) or Anthropic (cloud).

The LLM never *finds* changes (pixels/text do that). It only explains a cropped
region, returning structured JSON. Every region is sent as ONE side-by-side
image so single-image models (Llama 3.2 Vision) work too.
"""
from __future__ import annotations

import base64
import json
import re

SEVERITIES = ("high", "medium", "low")


def parse_json(text):
    if not text:
        return None
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def normalize(d, domain):
    if not isinstance(d, dict):
        return None
    ctype = str(d.get("change_type", "other")).strip().lower()
    if ctype not in domain.change_types:
        ctype = "other"
    sev = str(d.get("severity", "medium")).strip().lower()
    if sev not in SEVERITIES:
        sev = "medium"
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0.5))))
    except Exception:
        conf = 0.5
    def s(v):
        return None if v in (None, "", "null") else str(v)
    return dict(change_type=ctype, description=str(d.get("description", "")).strip() or "Change detected",
                old=s(d.get("old")), new=s(d.get("new")), severity=sev, confidence=conf)


def build_prompt(domain, ctx_a, ctx_b):
    return (
        f"You are reviewing two revisions of a {domain.label}.\n"
        "The image shows the SAME region side by side: LEFT = revision A (old), RIGHT = revision B (new).\n"
        f"Text extracted from the PDFs near this region:\nA: {ctx_a or '(none)'}\nB: {ctx_b or '(none)'}\n"
        f"{domain.hint}\n"
        "Describe exactly what changed between LEFT and RIGHT. Do not invent values you cannot read; "
        "if unsure, say so and use a low confidence.\n"
        "Respond with ONLY a JSON object with keys: "
        f"change_type (one of {domain.change_types}), description (one sentence), "
        "old (string or null), new (string or null), severity (high|medium|low), confidence (0-1)."
    )


class LLM:
    name = "none"

    def _ask_image(self, prompt: str, png: bytes) -> str:  # pragma: no cover
        raise NotImplementedError

    def _ask_text(self, prompt: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def describe(self, png: bytes, ctx_a: str, ctx_b: str, domain):
        raw = self._ask_image(build_prompt(domain, ctx_a, ctx_b), png)
        d = normalize(parse_json(raw), domain)
        if d is None:
            d = dict(change_type="other", description=(raw or "").strip()[:300] or "Change detected",
                     old=None, new=None, severity="medium", confidence=0.2)
        return d

    def summarize(self, changes, domain):
        lines = [f"- [{c['severity']}] [{c['page']}] {c['description']}" for c in changes[:80]]
        prompt = (
            f"Below is a list of detected differences between two revisions of a {domain.label}.\n"
            + "\n".join(lines)
            + "\n\nWrite a concise executive summary (4-6 sentences) of what changed, highlighting the "
              "highest-severity items. Use only facts from the list; do not invent anything."
        )
        return (self._ask_text(prompt) or "").strip()


class NoLLM(LLM):
    name = "none"

    def describe(self, *a, **k):
        return None

    def summarize(self, *a, **k):
        return None


class OllamaLLM(LLM):
    def __init__(self, model="llama3.2-vision", host="http://localhost:11434"):
        self.model, self.host = model or "llama3.2-vision", host.rstrip("/")
        self.name = f"ollama:{self.model}"

    def _chat(self, content, images=None, as_json=False):
        import requests

        msg = {"role": "user", "content": content}
        if images:
            msg["images"] = images
        body = {"model": self.model, "messages": [msg], "stream": False, "options": {"temperature": 0}}
        if as_json:
            body["format"] = "json"
        r = requests.post(f"{self.host}/api/chat", json=body, timeout=300)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _ask_image(self, prompt, png):
        return self._chat(prompt, [base64.b64encode(png).decode()], as_json=True)

    def _ask_text(self, prompt):
        return self._chat(prompt)


class AnthropicLLM(LLM):
    def __init__(self, model="claude-sonnet-5-5"):
        import anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or "claude-sonnet-5-5"
        self.name = f"anthropic:{self.model}"

    def _ask_image(self, prompt, png):
        msg = self.client.messages.create(
            model=self.model, max_tokens=600,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(png).decode()}},
                {"type": "text", "text": prompt}]}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    def _ask_text(self, prompt):
        msg = self.client.messages.create(model=self.model, max_tokens=700,
                                          messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if b.type == "text")


def make_llm(backend="none", model=None, host="http://localhost:11434"):
    backend = (backend or "none").lower()
    if backend == "ollama":
        return OllamaLLM(model, host)
    if backend == "anthropic":
        return AnthropicLLM(model)
    return NoLLM()
