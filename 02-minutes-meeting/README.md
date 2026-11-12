# Meeting Minutes Creator

A private, on-device app that turns a meeting recording (or pasted transcript) into polished minutes: summary, discussion, decisions, action items with owners and deadlines, and open questions.

- **Speech to text:** faster-whisper (open-source Whisper, runs on CPU, no API key)
- **Writing the minutes:** Llama 3.2 through Ollama (open-weight, local)
- **Interface:** Streamlit
- **Ask the meeting:** transcript-grounded Q&A using local Ollama
- **Library:** local JSON meeting history (audio is not retained by default)
- **Export:** Word (.docx), PDF, Markdown, JSON, transcript text

Everything is free and nothing leaves your computer.

## Setup (Windows)

1. Install [Python 3.10+](https://www.python.org/downloads/) and [Ollama](https://ollama.com/download).
2. Double-click **setup.bat** (creates `venv`, installs packages, runs `ollama pull llama3.2`).
3. Double-click **run.bat**. The app opens in your browser.

Or manually in PowerShell:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
ollama pull llama3.2
streamlit run app.py
```

The first transcription downloads the Whisper model once (about 150 MB for `base`), then works offline.

## Using it

1. Upload a recording, or paste a transcript.
2. Pick the transcription quality, language and level of detail in the sidebar.
3. Click **Generate minutes**, review, then download as Word or Markdown.

## Tips

- Slow laptop? Use `tiny` or `base`. Want better accuracy? Use `small`.
- Long meetings are split into parts automatically and merged at the end.
- Whisper does not identify who is speaking. Attendee/name hints improve spelling but do not identify speakers. Optional diarization is available through `src/diarize.py` and requires pyannote plus an authorized Hugging Face token.
- Small models can miss details or misattribute owners, so always review before sharing.

## Project layout

```
app.py              Streamlit interface
src/transcribe.py   Whisper transcription
src/qa.py           Transcript-grounded Q&A
src/diarize.py      Optional pyannote speaker diarization
src/store.py        Local JSON meeting library
src/summarize.py    Ollama prompts, chunking, JSON cleanup
src/export.py       Word, PDF and Markdown export
src/config.py       Model names and settings
tests/              Unit tests (python -m pytest)
outputs/            Word copies are saved here
```

## Additional features

- Choose a summary style: Professional, Short & concise, Story-oriented, or Action-focused.
- Ask questions about the current meeting. Answers are grounded in retrieved transcript excerpts; if the transcript does not contain the answer, the assistant should say so.
- Generated meetings are saved as local JSON records under `meetings/`. Uploaded audio is not retained by default.
- PDF export is available alongside Word, Markdown, JSON and transcript downloads.
- Whisper timestamps are passed into the minutes prompt. Timestamp accuracy depends on transcription quality and the model's ability to preserve them.
- Optional speaker diarization uses pyannote. It requires accepting the model terms on Hugging Face, a token with access, and the optional package: `pip install pyannote.audio`. Speaker labels are anonymous (`SPEAKER_00`, etc.) unless manually mapped to names.

## Tests

```powershell
python -m pytest -q
```

## Privacy note

The app is designed for local processing. The optional pyannote model may be downloaded from Hugging Face when first used. Keep meeting recordings and generated notes private, and get consent before recording or processing other people's conversations.
