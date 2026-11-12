# TriageLens

A local web app for screening newly submitted biomedical manuscripts. For each submission it
tells you the category, which compliance checks apply (PRISMA, ethics, AI code/data, dataset
accessions, validation of in-silico results) and which specialty should take it. It uses a
Llama model running on **your own machine** through Ollama, so unpublished work never leaves it.

## Features

- Queue view with tabs (New, Analyzed, Assigned, Done), search, and filters by category, specialty and check
- Llama analysis per submission: category, study type, one-line summary, suggested specialty,
  checks required, points to double-check, confidence and a short reason
- Rule engine that always flags the obvious checks; Llama can add checks but never remove one,
  and its output is forced into your allowed specialties and checks
- Detail panel: paste an abstract and re-analyze, tick checks off as you complete them,
  override the specialty, assign to a person, keep notes, copy a summary for a message
- Duplicate-title warning, queue insights, CSV import and export
- Editable specialties, checks and assignee names in Settings, no code changes needed
- Falls back to rules only if Ollama is not running, and tells you so

## Setup

1. Install Python 3.10+ and Ollama (https://ollama.com/download)
2. Pull a model that fits your RAM:
   ```
   ollama pull llama3.1:8b      # good default, about 8 GB RAM
   ollama pull llama3.2:3b      # lighter, less accurate
   ```
3. Install and run:
   ```
   pip install -r requirements.txt
   python run.py
   ```
4. Your browser opens at http://localhost:8000. Click **Load sample queue**, then **Analyze all new**.

The first screen shows a green "Llama ready" pill when Ollama is reachable. Pick a different
model in **Settings**.

## Using it

- **Add submissions:** paste titles (one per line), upload a CSV with a header row
  `id,title,abstract,tags` (only `title` is required, separate tags with `;`), or add one
  with its abstract. An example is in `sample_input.csv`.
- **Add abstracts.** With titles alone the model is told to lower its confidence, and results are rough.
- **Settings:** set the model, the names that appear in the Assign menu, and the rules JSON.
  Replace the placeholder specialty names with your real teams and adjust the keywords.
- **Export CSV** gives you everything: status, specialty, assignee, checks required and done, notes.
- Keyboard: `/` focuses search, `Esc` closes the detail panel.

## Docker (optional)

```
docker build -t triagelens .
docker run -p 8000:8000 -v triagelens-data:/data \
  -e OLLAMA_URL=http://host.docker.internal:11434 triagelens
```
On Linux add `--add-host=host.docker.internal:host-gateway`.

## Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI backend and API |
| `triage.py` | Rules plus Llama analysis |
| `db.py` | SQLite storage (data lives in `data/triage.db`) |
| `rules.json` | Default specialties and checks (copied to `data/rules.json`, edit in Settings) |
| `static/` | The website: `index.html`, `app.css`, `app.js` |

Environment variables: `OLLAMA_URL` (default http://localhost:11434), `OLLAMA_MODEL`,
`PORT`, `HOST`, `DATA_DIR`.

## Important

This is a triage aid, not a decision-maker. A human editor should confirm every classification,
check and assignment. It runs only on localhost by default, with no login, so do not expose it
on a shared network without adding authentication. Not affiliated with any publisher.
