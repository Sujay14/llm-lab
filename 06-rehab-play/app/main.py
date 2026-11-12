from pathlib import Path
import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
BASE = Path(__file__).resolve().parent
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5:3b")

app = FastAPI(title="REHAB PLAY", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model: str = Field(default="", max_length=120)
    context: str = Field(default="", max_length=3000)

@app.get("/")
async def home(): 
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
        return {"status": "online", "ollama": True, "models": models, "default_model": DEFAULT_MODEL}
    except Exception:
        return {"status": "online", "ollama": False, "models": [], "default_model": DEFAULT_MODEL}

@app.post("/api/assistant")
async def assistant(payload: ChatRequest):
    system = """You are REHAB PLAY's educational rehabilitation companion. You are NOT a clinician, doctor, physiotherapist, diagnostic system, or treatment planner.
You may explain general rehabilitation concepts in plain language, help users understand clinician-provided instructions, organize questions for their physiotherapist, and summarize user-entered session logs.
Never diagnose, prescribe exercises, change exercise dosage, set repetitions, recommend progression, assess injury severity, or tell someone an exercise is safe for their condition.
When users ask what exercise they should do, ask them to follow their own clinician-approved plan and offer to help interpret instructions they provide. Never infer a treatment plan from symptoms.
If the user reports new/severe pain, chest pain, fainting, severe breathlessness, sudden weakness/numbness, or an acute concerning symptom, advise stopping the activity and seeking appropriate urgent medical help. For routine pain or symptom concerns, advise pausing the activity and contacting their treating clinician.
Be warm, concise, accessible, and clear about uncertainty. Do not make claims about recovery outcomes."""
    user = payload.message
    if payload.context.strip():
        user += "\n\nUSER-PROVIDED SESSION CONTEXT (summarize only; do not treat as clinical instructions):\n" + payload.context
    model = payload.model.strip() or DEFAULT_MODEL
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "options": {"temperature": 0.35, "num_predict": 500},
                },
            )
            r.raise_for_status()
            data = r.json()
        return {"reply": data.get("message", {}).get("content", ""), "model": data.get("model", model)}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama is not reachable. Start Ollama on the host computer.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc.response.text[:500]}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The local model timed out. Try a shorter message.")
