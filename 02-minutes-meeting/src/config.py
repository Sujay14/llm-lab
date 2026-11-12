"""Central settings. Everything runs locally and uses free, open-weight models."""
from pathlib import Path

APP_NAME = "Meeting Minutes Creator"
APP_TAGLINE = "Private, on-device minutes from any meeting recording"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs"

# --- Language model (Ollama) -------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
OLLAMA_NUM_CTX = 8192
OLLAMA_TEMPERATURE = 0.2

# Roughly 7,000 characters is about 1,750 tokens, which leaves plenty of room
# for the prompt and the JSON answer inside the context window.
CHUNK_CHARS = 7000

# --- Speech to text (faster-whisper, runs on CPU, no API key) ----------------
WHISPER_SIZES = ["tiny", "base", "small", "medium"]
DEFAULT_WHISPER = "base"

LANGUAGES = {
    "Auto-detect": None,
    "English": "en",
    "Hindi": "hi",
    "Kannada": "kn",
    "Tamil": "ta",
    "Telugu": "te",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
}

AUDIO_TYPES = ["mp3", "wav", "m4a", "mp4", "ogg", "flac", "webm"]

DETAIL_LEVELS = {
    "Concise": "Keep every item short: one sentence each, and at most five discussion points.",
    "Standard": "Balance brevity and completeness: one or two sentences per item.",
    "Detailed": "Be thorough: capture reasoning, context and nuance for every discussion point.",
}
