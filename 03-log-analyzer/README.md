# LOGSCOPE AI

Local-first DevOps log analyzer: FastAPI + Jinja2 + SQLite + Ollama.

## Requirements
- Python 3.10+
- Ollama installed and running
- `qwen2.5:3b` for text analysis
- `qwen2.5vl:3b` for screenshot analysis

## Windows PowerShell setup
```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5vl:3b
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000. API docs: http://127.0.0.1:8000/docs.

## Linux/macOS
```bash
ollama pull qwen2.5:3b
ollama pull qwen2.5vl:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Tests
```bash
pytest -q
```

## API
- GET `/health`
- POST `/api/analyze` multipart `file`
- POST `/api/analyze-image` multipart `file`
- GET `/api/incidents`
- GET `/api/incidents/{id}`
- POST `/api/chat` JSON `{"incident_id":1,"question":"Why did this fail?"}`

## Notes and safety
The deterministic rule engine scans the full uploaded log; Ollama receives bounded excerpts to fit local context. Image uploads are sent to the local vision model and are not saved as incidents. Human-error signals are leads, not proof; correlate them with authoritative audit logs. Secret masking is basic and cannot guarantee complete redaction. Do not upload credentials or customer data. Review every suggested command before running it, especially in production. This starter is not a production observability replacement and its signatures need to be expanded against your environment's real logs.


## Extended diagnostics
- Dockerfile instruction checks (not a full BuildKit parser).
- Jenkinsfile/Groovy delimiter checks (not a full Groovy compiler).
- YAML syntax validation using PyYAML.
- Repeated-error and simple error-density anomaly heuristics.
- Component-keyed event grouping and audit-command actor extraction when identity fields are present.
- PDF incident report at `GET /api/incidents/{id}/report.pdf`.

These are explainable starter diagnostics, not a substitute for Docker build, Jenkins Pipeline Linter, Kubernetes API validation, SIEM audit trails or statistical monitoring.
