from dotenv import load_dotenv
load_dotenv()
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
(ROOT/"data").mkdir(exist_ok=True)
OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL","http://localhost:11434").rstrip("/")
TEXT_MODEL=os.getenv("OLLAMA_TEXT_MODEL","qwen2.5:3b")
VISION_MODEL=os.getenv("OLLAMA_VISION_MODEL","qwen2.5vl:3b")
MAX_UPLOAD_MB=int(os.getenv("MAX_UPLOAD_MB","25"))
DB=os.getenv("DATABASE_PATH",str(ROOT/"data/logscope.db"))
