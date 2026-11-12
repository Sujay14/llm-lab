# Medical Report Assistant

Upload your own lab report (PDF), then ask questions in plain language. The app finds the relevant
parts of the report and explains them in simple English, **with page numbers**. Everything runs on
your own computer; nothing is sent to the cloud.

> **Educational use only.** This is not a doctor and not a diagnostic tool. It never diagnoses,
> prescribes, or tells you to start/stop/change treatment. Discuss your results with a qualified
> healthcare professional.

## This is RAG, not model training

The app does **not** train or fine-tune Llama on your PDF. The model's weights never change.

```
PDF -> extract text (per page) -> split into chunks -> embeddings (nomic-embed-text)
    -> store in ChromaDB -> embed your question -> retrieve the most similar chunks
    -> send question + those excerpts to llama3.2 -> answer + source pages
```

The PDF is only a *source document for retrieval*. Each question is answered from the excerpts
found for that question. Because nothing is learned, the report can be forgotten instantly
(**Upload another report**) and a new one never mixes with the old one.

## Tech stack

Python · Ollama (`llama3.2` for answers, `nomic-embed-text` for embeddings) · PyMuPDF · ChromaDB ·
Streamlit. No LangChain / LlamaIndex.

## 1. Install Ollama and the models (Windows 10/11)

1. Install Ollama: https://ollama.com/download/windows (leave it running in the background).
2. In PowerShell:

```powershell
ollama pull llama3.2
ollama pull nomic-embed-text
```

## 2. Set up the project (VS Code terminal / PowerShell)

Open the `medical-rag` folder, then:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If PowerShell refuses to run `activate`, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 3. Run

```powershell
streamlit run app.py
```

Open http://localhost:8501 if it does not open by itself.

## 4. Use it

1. Upload a text-based lab report PDF.
2. Click **Process report** (progress bar shows reading, embedding, saving).
3. Ask questions in the chat, or open **Suggested questions**. Ask follow-ups freely.
4. **Upload another report** wipes the old one completely.

Each answer has: **What the report says** · **What it means** · **Source page(s)** · a short disclaimer.
The source pages are the pages the retrieved excerpts came from. They are added by the app, not
written by the model.

### About page numbers

Some PDFs are several reports merged together, each with its own printed numbering
(for example "Page 1 of 17" … then "Page 1 of 9"). The app therefore always shows the **PDF page**
(what your PDF viewer shows) and, when present, the printed label:
`PDF page 19 (printed "Page 1 of 9")`.

## How it handles lab-report layouts

* **Table pages** (`Test | Result | Unit | Range`) are rebuilt row by row, so a result stays next to its
  test name. (PyMuPDF's default order separates them.)
* **Card pages** keep PyMuPDF's block order, which already groups a result with its range.
* **Colour-dot flags.** Some reports flag a result only with a red/green dot, which is not text. The
  app reads those dots from the PDF drawing data and adds a tag such as
  `Neutrophils: 49.6 % [Report marker: red dot]` so the model can see it. A dot with no clear owner is
  skipped rather than guessed.
* **Identifiers** (name, lab/registration IDs, header dates/centre) are removed before indexing, so
  they are not stored, shown or logged. This is best effort; check any new report layout.
* Repeated letterhead/footer lines are removed so they do not pollute search results.

## Settings (`config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `LLM_MODEL` / `EMBED_MODEL` | `llama3.2` / `nomic-embed-text` | Ollama model names |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 900 / 120 | characters per chunk / shared between neighbours |
| `TOP_K` | 5 | chunks retrieved per question |
| `BROAD_TOP_K` | 10 | chunks for "summarize" / "which results are flagged" style questions |
| `MAX_DISTANCE` | 0.85 | best match farther than this => "weak match" (see tuning below) |
| `NUM_CTX` | 8192 | context window requested from Ollama |

Models can also be overridden with the `MRA_LLM_MODEL` and `MRA_EMBED_MODEL` environment variables.

**Tuning retrieval:** tick **Developer view** in the sidebar to see the retrieved excerpts and their
distances. If good answers are labelled "No closely matching section", raise `MAX_DISTANCE`; if
unrelated text is retrieved, lower it or reduce `TOP_K`.

## Limitations (please read)

* **Temporary storage.** The report lives in memory only. It disappears when the app restarts or you
  upload another report. This is a single-user local tool, not a production multi-user system.
* **No OCR.** Scanned / image-only PDFs are rejected with a clear message.
* **Small local model.** `llama3.2` is a small model. It can misread tables or miss a result.
  Always check the quoted values and page against the PDF itself.
* **Retrieval can miss.** Only the top few chunks are sent to the model. If an answer says the report
  lacks information that you can see in the PDF, try naming the test exactly, or ask again.
* **No diagnosis.** It explains printed values and ranges only.

## Tests

```powershell
python -m pytest -q tests
```

The unit tests use small synthetic PDFs (never a real patient report). `tests/fake_ollama.py` is a
stand-in Ollama server (hash-based embeddings, canned replies) for checking the plumbing without
models: `python tests/fake_ollama.py` then run the app. It cannot judge answer quality.

## Privacy

* Never commit a real report. `.gitignore` excludes `*.pdf` and `data/*`.
* The app does not log report text and never displays the uploaded file's name.
* Use reports only with permission. Remove identifiers before sharing screenshots.

## Troubleshooting

| Message / symptom | Fix |
|---|---|
| "Cannot reach Ollama" | Start the Ollama app (system tray). Test: `ollama list` |
| "The model 'llama3.2' is not installed" | `ollama pull llama3.2` |
| "The model 'nomic-embed-text' is not installed" | `ollama pull nomic-embed-text` |
| "No selectable text was found" | The PDF is scanned. OCR is not included. |
| "could not be opened as a PDF" / password-protected | Re-download the PDF; remove any password |
| Very slow answers | Normal on CPU-only PCs. Lower `BROAD_TOP_K` or `NUM_CTX` in `config.py` |
| Out-of-memory when answering | Lower `NUM_CTX` (e.g. 4096) |
| `pip install` fails for chromadb | Upgrade pip: `python -m pip install -U pip`, use Python 3.10-3.13 |

Technical details (never report text) are printed in the terminal window running Streamlit.

## Project layout

```
app.py                      Streamlit UI
config.py                   settings
services/pdf_processor.py   page-by-page extraction, layout handling, identifier removal
services/text_chunker.py    overlapping chunks that keep page numbers
services/embedding_service.py  Ollama embeddings
services/vector_store.py    ChromaDB (one isolated in-memory collection per report)
services/llm_service.py     grounded prompt + streamed Ollama chat
services/rag_pipeline.py    ingest + retrieve steps used by app.py
services/ollama_client.py   connection, health check, friendly errors
utils/prompt_templates.py   all model instructions and fixed wording
utils/errors.py             user-friendly error types
tests/                      unit tests + stub Ollama server
```
