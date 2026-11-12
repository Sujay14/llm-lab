import httpx
from app.config import OLLAMA_URL, REQUEST_TIMEOUT

async def get_models():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{OLLAMA_URL}/api/tags")
        r.raise_for_status()
        return r.json().get("models", [])

async def run_chat(model, system, user, temperature=0.3, max_tokens=700):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
    return {
        "response": data.get("message", {}).get("content", ""),
        "model": data.get("model", model),
        "total_duration_ms": round(data.get("total_duration", 0) / 1_000_000, 2),
        "prompt_tokens": data.get("prompt_eval_count"),
        "generated_tokens": data.get("eval_count"),
    }

async def stream_chat(model, system, user, temperature=0.3, max_tokens=700):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    yield line
