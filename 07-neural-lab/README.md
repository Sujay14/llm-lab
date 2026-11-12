# NEURAL LAB 86 - LLM Workbench

A lightweight green-terminal website with real local LLM task execution through Ollama.

## Features
- Sentiment analysis
- Named entity recognition
- Context-based question answering
- Translation
- Summarization
- Text classification
- Information extraction
- Paraphrasing
- Text generation
- Next-text continuation
- Custom system-prompt laboratory
- Model selection from installed Ollama models
- Temperature and output-length controls
- Normal responses and streaming output
- Shows inference timing and token counts when Ollama returns them

## Requirements
- Python 3.10+
- Ollama installed and running
- At least one model downloaded

This project defaults to `qwen2.5:3b`, which you already installed for your earlier LOGSCOPE work.

## Windows PowerShell setup

```powershell
# In this project directory
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env

# Start Ollama if it is not already running
ollama serve

# In another terminal, start the website
uvicorn app.main:app --reload --port 8003
```

Open http://127.0.0.1:8003

API docs: http://127.0.0.1:8003/docs  
Health: http://127.0.0.1:8003/api/health

If Ollama is already running as a background service, do not start a second `ollama serve` process.

## Configure
Edit `.env`:
```env
OLLAMA_URL=http://localhost:11434
DEFAULT_MODEL=qwen2.5:3b
REQUEST_TIMEOUT=180
```

Restart Uvicorn after changing `.env`.

## Accuracy and limitations
- The selected Ollama model performs the actual NLP tasks. JSON is requested through task-specific prompts but is not guaranteed unless the model follows the instruction.
- Next-text continuation is a real model continuation. The standard Ollama chat endpoint used here does not expose logits or exact next-token probability distributions.
- Streaming chunks are pieces of generated text and are not guaranteed to align one-to-one with tokenizer tokens.
- Tokenization and token-ID inspection are not implemented in this workbench yet; exact IDs require the tokenizer corresponding to the selected model.
- Use a context passage for QA. The QA instruction tells the model to answer from that context and admit when evidence is missing.
- Outputs are educational and should be checked, especially for high-impact decisions.
