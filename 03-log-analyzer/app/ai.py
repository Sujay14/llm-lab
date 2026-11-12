import httpx,base64
from app.config import OLLAMA_BASE_URL,TEXT_MODEL,VISION_MODEL
async def ask(prompt,model=TEXT_MODEL,images=None):
 payload={"model":model,"prompt":prompt,"stream":False,"options":{"temperature":0.1,"num_ctx":8192}}
 if images: payload["images"]=images
 async with httpx.AsyncClient(timeout=180) as c:
  r=await c.post(OLLAMA_BASE_URL+"/api/generate",json=payload); r.raise_for_status()
  return r.json().get("response","")
async def investigate(logs,analysis):
 return await ask("You are LOGSCOPE, a cautious DevOps investigator. Use only supplied evidence. Separate facts from hypotheses. Never invent actors, pod names or metrics. Do not claim human error without audit evidence. Give Summary, Likely explanation, Evidence, Unknowns, Next checks and Safe remediation.\nAnalysis: "+str(analysis)+"\nLogs:\n"+logs[:14000])
async def chat(logs,analysis,question):
 return await ask("Answer only from this incident context; admit missing evidence. Give safe diagnostic steps.\nContext:"+str(analysis)[:8000]+"\nLogs:"+logs[:8000]+"\nQuestion:"+question)
async def vision(raw):
 return await ask("Read this terminal/log screenshot accurately. Separate visible text from interpretation. Never invent unreadable content.",VISION_MODEL,[base64.b64encode(raw).decode()])
