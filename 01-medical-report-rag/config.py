"""Central settings. Change values here (or override a few with environment variables)."""
import os

# --- Models (run locally through Ollama) ---
LLM_MODEL = os.getenv("MRA_LLM_MODEL", "llama3.2")
EMBED_MODEL = os.getenv("MRA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")  # None -> Ollama default (http://localhost:11434)

# --- Chunking (characters) ---
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120

# --- Retrieval ---
TOP_K = 3             # chunks retrieved for a normal question (3-5 recommended)
BROAD_TOP_K = 6      # chunks for "summarize" / "which results are flagged" style questions
MAX_DISTANCE = 0.85   # cosine distance above which the best match is treated as "weak"
EMBED_BATCH_SIZE = 16

# --- Generation ---
NUM_CTX = 4096        # context window requested from Ollama
TEMPERATURE = 0.0     # low = more faithful to the excerpts
HISTORY_TURNS = 3     # previous question/answer pairs sent to the model for follow-ups

# --- PDF limits ---
MAX_PAGES = 150
MIN_PAGE_CHARS = 30   # pages with less content than this (e.g. header only) are skipped
MIN_TEXT_CHARS = 40   # fewer extractable characters than this => treated as "no text"
