import json,re
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,HTTPException,Request
from fastapi.responses import HTMLResponse, StreamingResponse
from io import BytesIO
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.config import MAX_UPLOAD_MB
from app.db import init,save,get,all
from app.analyzer import analyze, enrich
from app.advanced import validate_config
from app.ai import investigate,chat,vision
app=FastAPI(title="LOGSCOPE AI")
HERE=Path(__file__).parent
app.mount("/static",StaticFiles(directory=HERE/"static"),name="static")
templates=Jinja2Templates(directory=HERE/"templates")
@app.on_event("startup")
def startup(): init()
@app.get("/",response_class=HTMLResponse)
async def home(request:Request): return templates.TemplateResponse(request,"index.html",{"incidents":all()})
@app.get("/health")
async def health(): return {"status":"ok"}
@app.post("/api/analyze")
async def upload(file:UploadFile=File(...)):
 if Path(file.filename or "").suffix.lower() not in {".log",".txt",".json",".csv",".out",".yaml",".yml",".groovy",".dockerfile"} and Path(file.filename or "").name.lower() not in {"dockerfile","jenkinsfile"}: raise HTTPException(400,"Use .log, .txt, .json, .csv or .out")
 raw=await file.read(MAX_UPLOAD_MB*1024*1024+1)
 if len(raw)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,"File too large")
 logs=raw.decode("utf-8",errors="replace")
 logs=re.sub(r"(?i)(password|token|secret|api[_-]?key)(\s*[:=]\s*)[^\s,;]+",r"\1\2[REDACTED]",logs)
 result=enrich(logs,analyze(logs,file.filename or "upload.log"))
 result["findings"].extend(validate_config(file.filename or "upload.log",logs))
 try: result["ai_analysis"]=await investigate(logs,result)
 except Exception as e: result["ai_analysis"]=f"Ollama unavailable ({type(e).__name__}). Rule-based analysis is still available. Start Ollama and pull the configured model."
 result["filename"]=file.filename or "upload.log"
 result["incident_id"]=save(result["filename"],result["source_type"],result,logs)
 return result
@app.post("/api/analyze-image")
async def image_upload(file:UploadFile=File(...)):
 if not (file.content_type or "").startswith("image/"): raise HTTPException(400,"Upload an image")
 raw=await file.read(MAX_UPLOAD_MB*1024*1024+1)
 if len(raw)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(413,"Image too large")
 try: return {"analysis":await vision(raw)}
 except Exception as e: raise HTTPException(503,"Vision model unavailable. Check Ollama and qwen2.5vl:3b.")
@app.get("/api/incidents")
async def incidents(): return all()
@app.get("/api/incidents/{iid}")
async def incident(iid:int):
 r=get(iid)
 if not r: raise HTTPException(404,"Incident not found")
 d=json.loads(r["result"]); d["incident_id"]=iid; return d
class ChatBody(BaseModel):
 incident_id:int
 question:str
@app.post("/api/chat")
async def ask_chat(body:ChatBody):
 r=get(body.incident_id)
 if not r: raise HTTPException(404,"Incident not found")
 try: return {"answer":await chat(r["logs"],json.loads(r["result"]),body.question[:2000])}
 except Exception: raise HTTPException(503,"Ollama is unavailable")

@app.get("/api/incidents/{iid}/report.pdf")
async def incident_pdf(iid:int):
    row=get(iid)
    if not row: raise HTTPException(404,"Incident not found")
    data=json.loads(row["result"])
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from xml.sax.saxutils import escape
    except ImportError:
        raise HTTPException(503,"Install reportlab from requirements.txt")
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm)
    styles=getSampleStyleSheet()
    story=[Paragraph("LOGSCOPE AI - Incident Report",styles["Title"]),
           Paragraph("Incident #"+str(iid)+": "+escape(row["filename"]),styles["Heading2"]),
           Paragraph("Source: "+escape(row["source"]),styles["Normal"]),Spacer(1,10),
           Paragraph("Executive summary",styles["Heading2"]),
           Paragraph(escape(data.get("summary","")),styles["BodyText"]),Spacer(1,8),
           Paragraph("Findings",styles["Heading2"])]
    for f in data.get("findings",[]):
        story += [Paragraph(escape(f.get("severity","").upper()+": "+f.get("title","")),styles["Heading3"]),
                  Paragraph(escape(f.get("description","")),styles["BodyText"])]
        for ev in f.get("evidence",[])[:5]: story.append(Paragraph("Evidence: "+escape(ev),styles["BodyText"]))
        for rec in f.get("recommendations",[])[:6]: story.append(Paragraph("Recommended: "+escape(rec),styles["BodyText"]))
        story.append(Spacer(1,6))
    story += [Paragraph("AI investigation",styles["Heading2"]),
              Paragraph(escape(data.get("ai_analysis","No AI analysis")).replace("\n","<br/>")[:12000],styles["BodyText"]),
              Paragraph("Anomalies",styles["Heading2"])]
    for a in data.get("anomalies",[]): story.append(Paragraph(escape(a.get("description","")),styles["BodyText"]))
    for c in data.get("correlations",[]): story.append(Paragraph(escape(f"{c['component']}: {c['event_count']} related events, lines {c['first_line']}-{c['last_line']}"),styles["BodyText"]))
    doc.build(story); buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="logscope-incident-{iid}.pdf"'})
