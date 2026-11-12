"""A tiny stand-in for the Ollama HTTP API, for testing WITHOUT a GPU or model downloads.

Embeddings are hashed bag-of-words vectors (lexical, not semantic) and chat replies are canned.
It verifies the plumbing (PDF -> chunks -> Chroma -> retrieval -> streamed answer -> UI), not model quality.
Run:  python tests/fake_ollama.py [port]
"""
import json
import re
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = 512
MODELS = ["llama3.2:latest", "nomic-embed-text:latest"]


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        vec[zlib.crc32(tok.encode()) % DIM] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [{"name": m, "model": m, "size": 1, "digest": "x"} for m in MODELS]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        model = data.get("model", "")
        if not any(model == m or m.startswith(model + ":") for m in MODELS):
            return self._json({"error": f"model '{model}' not found"}, 404)
        if self.path == "/api/embed":
            inputs = data["input"] if isinstance(data["input"], list) else [data["input"]]
            return self._json({"model": model, "embeddings": [embed(t) for t in inputs]})
        if self.path == "/api/chat":
            last = data["messages"][-1]["content"]
            pages = sorted({int(p) for p in re.findall(r"\[PDF page (\d+)\]", last)})
            text = (
                "**What the report says**\n- [STUB ANSWER] Excerpts were supplied from PDF page(s) "
                f"{', '.join(map(str, pages)) or 'none'}.\n\n**What it means**\n- This is a canned reply from the test stub."
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            words = text.split(" ")
            for i, w in enumerate(words):
                line = {"model": model, "message": {"role": "assistant", "content": w + (" " if i < len(words) - 1 else "")}, "done": False}
                self.wfile.write((json.dumps(line) + "\n").encode())
            self.wfile.write((json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}) + "\n").encode())
            return
        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11434
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
