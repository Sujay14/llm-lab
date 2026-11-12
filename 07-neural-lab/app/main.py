import json
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import DEFAULT_MODEL
from app.ollama import get_models, run_chat, stream_chat
from app.schemas import RunRequest
from app.tasks import TASKS

BASE = Path(__file__).resolve().parent
app = FastAPI(title="NEURAL LAB 86 - LLM Workbench", version="0.3.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

def build_prompt(payload: RunRequest) -> tuple[str, str]:
    task = TASKS.get(payload.task)
    if not task:
        raise HTTPException(status_code=400, detail="Unknown task")
    system = task["system"]
    if payload.task == "translation":
        system += f"\nTarget language: {payload.target_language}."
    elif payload.task == "paraphrase":
        system += f"\nRequested style: {payload.style}."
    elif payload.task == "custom" and payload.custom_system.strip():
        system = payload.custom_system.strip()
    user = f"INPUT TEXT:\n{payload.text}"
    if payload.context.strip():
        user += f"\n\nCONTEXT / REFERENCE MATERIAL:\n{payload.context}"
    if payload.task == "qa":
        user += "\n\nAnswer the question in INPUT TEXT using only CONTEXT / REFERENCE MATERIAL."
    return system, user

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"default_model": DEFAULT_MODEL})

@app.get("/api/health")
async def health():
    try:
        models = await get_models()
        return {"status": "ok", "ollama": "connected", "models": [m.get("name") for m in models]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama at configured URL: {exc}")

@app.get("/api/models")
async def models():
    try:
        return {"models": [m.get("name") for m in await get_models()]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {exc}")

@app.post("/api/run")
async def run(payload: RunRequest):
    system, user = build_prompt(payload)
    model = payload.model.strip() or DEFAULT_MODEL
    try:
        result = await run_chat(model, system, user, payload.temperature, payload.max_tokens)
        return {
            "task": payload.task,
            "task_label": TASKS[payload.task]["label"],
            "model": result["model"],
            "response": result["response"],
            "total_duration_ms": result["total_duration_ms"],
            "prompt_tokens": result["prompt_tokens"],
            "generated_tokens": result["generated_tokens"],
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise HTTPException(status_code=502, detail=f"Ollama returned {exc.response.status_code}: {detail}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not contact Ollama: {exc}")

@app.post("/api/stream")
async def stream(payload: RunRequest):
    system, user = build_prompt(payload)
    model = payload.model.strip() or DEFAULT_MODEL

    async def events():
        try:
            async for line in stream_chat(model, system, user, payload.temperature, payload.max_tokens):
                try:
                    obj = json.loads(line)
                    message = obj.get("message", {}).get("content", "")
                    if message:
                        yield f"data: {json.dumps({'chunk': message})}\n\n"
                    if obj.get("done"):
                        yield f"data: {json.dumps({'done': True, 'model': obj.get('model', model)})}\n\n"
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
