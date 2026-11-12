"""Meeting Minutes Creator — a private, local Streamlit app (Whisper + Llama 3.2 via Ollama)."""
from __future__ import annotations

import html
import json
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from src import config
from src.export import slugify, to_docx_bytes, to_markdown, to_pdf_bytes
from src.summarize import OllamaUnavailable, check_ollama, generate_minutes
from src.transcribe import format_duration, format_transcript, transcribe_file
from src.qa import answer_question 
from src.store import list_meetings, save_meeting
from src.diarize import diarize_file, assign_speakers

st.set_page_config(page_title=config.APP_NAME, page_icon="📝", layout="wide")

# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

:root { --navy:#1B2A49; --gold:#B08D57; --ivory:#FAF8F3; --sand:#F1EDE4; --line:#E2DCCD; --muted:#6B7280; }

html, body, [class*="css"], .stApp { font-family: 'Inter', 'Segoe UI', sans-serif; }
.stApp { background: var(--ivory); }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.6rem; max-width: 1180px; }

.hero {
  background: linear-gradient(135deg, #14203A 0%, #1B2A49 55%, #26385F 100%);
  border-radius: 18px; padding: 2.1rem 2.4rem; margin-bottom: 1.6rem;
  box-shadow: 0 10px 30px rgba(20, 32, 58, .18); position: relative; overflow: hidden;
}
.hero::after {
  content: ""; position: absolute; right: -60px; top: -60px; width: 220px; height: 220px;
  border-radius: 50%; border: 1px solid rgba(176,141,87,.45);
}
.hero .kicker { color: var(--gold); letter-spacing: .24em; font-size: .72rem; font-weight: 600; text-transform: uppercase; }
.hero h1 { font-family: 'Cormorant Garamond', Georgia, serif; color: #fff; font-size: 2.7rem; font-weight: 600; margin: .25rem 0 .2rem; line-height: 1.1; }
.hero p { color: #C9D1E3; margin: 0; font-size: .98rem; }
.hero .rule { width: 64px; height: 2px; background: var(--gold); margin: .9rem 0; }

.card {
  background: #fff; border: 1px solid var(--line); border-radius: 14px;
  padding: 1.35rem 1.6rem; margin-bottom: 1rem; box-shadow: 0 2px 10px rgba(27,42,73,.04);
}
.card h3, .section-title {
  font-family: 'Cormorant Garamond', Georgia, serif; color: var(--navy);
  font-size: 1.45rem; font-weight: 700; margin: 0 0 .6rem; letter-spacing: .01em;
}
.section-title::after { content: ""; display: block; width: 34px; height: 2px; background: var(--gold); margin-top: .35rem; }
.card p, .card li { color: #2B2B2B; line-height: 1.65; font-size: .98rem; }
.card ul { padding-left: 1.1rem; margin: 0; }
.card li { margin-bottom: .45rem; }
.card li b { color: var(--navy); }

.meta-row { display: flex; flex-wrap: wrap; gap: .6rem; margin-bottom: 1.1rem; }
.chip { background: var(--sand); border: 1px solid var(--line); color: var(--navy); border-radius: 999px; padding: .28rem .85rem; font-size: .8rem; font-weight: 500; }
.minutes-title { font-family: 'Cormorant Garamond', Georgia, serif; color: var(--navy); font-size: 2.1rem; font-weight: 700; margin: .1rem 0 .6rem; }

table.actions { width: 100%; border-collapse: collapse; font-size: .93rem; }
table.actions th { background: var(--navy); color: #fff; text-align: left; padding: .6rem .8rem; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; font-weight: 600; }
table.actions th:first-child { border-top-left-radius: 8px; }
table.actions th:last-child { border-top-right-radius: 8px; }
table.actions td { padding: .65rem .8rem; border-bottom: 1px solid var(--line); color: #2B2B2B; vertical-align: top; }
table.actions tr:nth-child(even) td { background: #FBF9F4; }

.status { display: flex; align-items: center; gap: .55rem; font-size: .85rem; padding: .55rem .8rem; border-radius: 10px; border: 1px solid var(--line); background: #fff; }
.dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
.dot.ok { background: #3C9D6B; } .dot.bad { background: #C2543F; }

div.stButton > button[kind="primary"], div.stDownloadButton > button {
  border-radius: 10px; font-weight: 600; letter-spacing: .02em; padding: .55rem 1.4rem;
}
div.stButton > button[kind="primary"] { background: var(--navy); border: 1px solid var(--navy); color: #fff; }
div.stButton > button[kind="primary"]:hover { background: #26385F; border-color: var(--gold); color: #fff; }
section[data-testid="stSidebar"] { background: var(--sand); border-right: 1px solid var(--line); }
button[data-baseweb="tab"] { font-weight: 600; }
.empty { text-align: center; color: var(--muted); padding: 2.6rem 1rem; border: 1px dashed #D5CDBA; border-radius: 14px; background: rgba(255,255,255,.55); }
.privacy { color: var(--muted); font-size: .78rem; margin-top: 1.4rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.markdown(
    f"""
<div class="hero">
  <div class="kicker">Private · On-device · Free</div>
  <h1>{html.escape(config.APP_NAME)}</h1>
  <div class="rule"></div>
  <p>{html.escape(config.APP_TAGLINE)}. Whisper listens, Llama 3.2 writes, nothing leaves your laptop.</p>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown('<div class="section-title">Settings</div>', unsafe_allow_html=True)

    llm_model = st.text_input("Ollama model", value=config.OLLAMA_MODEL)
    status, message = check_ollama(config.OLLAMA_HOST, llm_model)
    st.markdown(
        f'<div class="status"><span class="dot {"ok" if status == "ok" else "bad"}"></span>{html.escape(message)}</div>',
        unsafe_allow_html=True,
    )
    if st.button("Re-check Ollama"):
        st.rerun()

    st.divider()
    whisper_size = st.selectbox(
        "Transcription quality",
        config.WHISPER_SIZES,
        index=config.WHISPER_SIZES.index(config.DEFAULT_WHISPER),
        help="tiny is fastest; small or medium is more accurate but slower on CPU.",
    )
    language_label = st.selectbox("Spoken language", list(config.LANGUAGES))
    detail = st.select_slider("Level of detail", options=list(config.DETAIL_LEVELS), value="Standard")
    summary_style = st.selectbox("Summary style", ["Professional", "Short & concise", "Story-oriented", "Action-focused"])
    name_hints = st.text_input("Names / technical terms for transcription (optional)", placeholder="Sujay, project names, acronyms")
    enable_diarization = st.checkbox("Identify speakers (optional, requires pyannote)")
    hf_token = st.text_input("Hugging Face token", type="password", disabled=not enable_diarization)

    st.divider()
    meeting_title = st.text_input("Meeting title (optional)")
    meeting_date = st.date_input("Meeting date", value=date.today())
    attendees = st.text_input("Attendees (optional)", placeholder="Asha, Ravi, Meera")

    st.markdown(
        '<div class="privacy">Audio and transcripts stay on this computer. '
        "Always review the minutes before sharing.</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #
left, right = st.columns([1.05, 1], gap="large")

with left:
    st.markdown('<div class="section-title">1 · Add your meeting</div>', unsafe_allow_html=True)
    tab_audio, tab_text = st.tabs(["Audio / video recording", "Paste transcript"])
    with tab_audio:
        upload = st.file_uploader(
            "Drop a recording", type=config.AUDIO_TYPES, label_visibility="collapsed"
        )
        st.caption("MP3, WAV, M4A, MP4, OGG, FLAC or WEBM.")
    with tab_text:
        pasted = st.text_area(
            "Transcript", height=220, label_visibility="collapsed",
            placeholder="Paste an existing transcript or notes here…",
        )
        transcript_file = st.file_uploader("…or upload a .txt file", type=["txt"], key="txt")

    generate = st.button("Generate minutes", type="primary", use_container_width=True)

with right:
    st.markdown('<div class="section-title">How it works</div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="card"><ul>
<li><b>Transcribe</b> — Whisper converts speech to text on your CPU.</li>
<li><b>Summarise</b> — Llama 3.2 (via Ollama) extracts decisions, actions and deadlines.</li>
<li><b>Export</b> — Download a polished Word document or Markdown file.</li>
</ul></div>
""",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Generate
# --------------------------------------------------------------------------- #
if generate:
    text_input = (pasted or "").strip()
    if transcript_file is not None and not text_input:
        text_input = transcript_file.getvalue().decode("utf-8", errors="ignore").strip()

    if upload is None and not text_input:
        st.warning("Please add a recording or paste a transcript first.")
    elif status != "ok":
        st.error(message)
    else:
        try:
            with st.status("Preparing your minutes…", expanded=True) as run:
                bar = st.progress(0.0)

                def tick(fraction: float, label: str) -> None:
                    bar.progress(min(max(fraction, 0.0), 1.0))
                    run.update(label=label)

                segments, transcript_text, duration = [], text_input, 0.0
                source = "Pasted transcript"

                if text_input == "" and upload is not None:
                    source = upload.name
                    suffix = Path(upload.name).suffix or ".mp3"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(upload.getvalue())
                        tmp_path = tmp.name
                    try:
                        result = transcribe_file(
                            tmp_path, whisper_size, config.LANGUAGES[language_label], tick,
                            initial_prompt=name_hints or None,
                        )
                        segments, duration = result.segments, result.duration
                        if enable_diarization:
                            turns = diarize_file(tmp_path, hf_token)
                            segments = assign_speakers(segments, turns)
                        transcript_text = format_transcript(segments, True) if segments else result.text
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)

                bar.progress(0.0)
                minutes = generate_minutes(
                    transcript_text,
                    model=llm_model,
                    host=config.OLLAMA_HOST,
                    detail=detail,
                    attendees=attendees,
                    progress=tick,
                    summary_style=summary_style,
                )
                run.update(label="Minutes are ready", state="complete", expanded=False)

            meta = {
                "title": meeting_title.strip() or minutes["title"] or "Meeting Minutes",
                "date": meeting_date.strftime("%d %B %Y"),
                "source": source,
                "duration": format_duration(duration) if duration else "",
                "attendees": attendees.strip(),
            }
            timestamped = format_transcript(segments, True) if segments else transcript_text
            st.session_state["result"] = {
                "minutes": minutes,
                "meta": meta,
                "transcript": timestamped,
            }
            save_meeting({"meta": meta, "minutes": minutes, "transcript": timestamped})

            config.OUTPUT_DIR.mkdir(exist_ok=True)
            (config.OUTPUT_DIR / f"{slugify(meta['title'])}.docx").write_bytes(
                to_docx_bytes(minutes, meta)
            )
        except (OllamaUnavailable, ValueError, RuntimeError) as exc:
            st.error(str(exc))
        except Exception as exc:  # keep the UI friendly for anything unexpected
            st.error(f"Something went wrong: {exc}")

# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
def esc(value: str) -> str:
    return html.escape(value or "")


def list_card(title: str, items: list[str]) -> None:
    if not items:
        return
    body = "".join(f"<li>{esc(i)}</li>" for i in items)
    st.markdown(f'<div class="card"><h3>{title}</h3><ul>{body}</ul></div>', unsafe_allow_html=True)


result = st.session_state.get("result")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown('<div class="section-title">2 · Your minutes</div>', unsafe_allow_html=True)

if not result:
    st.markdown(
        '<div class="empty">Your minutes will appear here, ready to review and download.</div>',
        unsafe_allow_html=True,
    )
else:
    minutes, meta = result["minutes"], result["meta"]
    tab_min, tab_tr, tab_qa, tab_dl, tab_library = st.tabs(["Minutes", "Transcript", "Ask this meeting", "Download", "Meeting library"])

    with tab_min:
        st.markdown(f'<div class="minutes-title">{esc(meta["title"])}</div>', unsafe_allow_html=True)
        chips = [meta["date"], meta["source"], meta["duration"]] + (
            [f"Attendees: {meta['attendees']}"] if meta["attendees"] else []
        )
        st.markdown(
            '<div class="meta-row">' + "".join(f'<span class="chip">{esc(c)}</span>' for c in chips if c) + "</div>",
            unsafe_allow_html=True,
        )

        if minutes["executive_summary"]:
            st.markdown(
                f'<div class="card"><h3>Executive summary</h3><p>{esc(minutes["executive_summary"])}</p></div>',
                unsafe_allow_html=True,
            )
        list_card("Participants", minutes["participants"])

        if minutes["discussion_points"]:
            body = "".join(
                f"<li><b>{'[' + esc(p.get('timestamp', '')) + '] ' if p.get('timestamp') else ''}{esc(p['topic'])}</b> — {esc(p['detail'])}</li>" if p["topic"] else f"<li>{'[' + esc(p.get('timestamp', '')) + '] ' if p.get('timestamp') else ''}{esc(p['detail'])}</li>"
                for p in minutes["discussion_points"]
            )
            st.markdown(f'<div class="card"><h3>Discussion</h3><ul>{body}</ul></div>', unsafe_allow_html=True)

        list_card("Decisions", minutes["decisions"])

        if minutes["action_items"]:
            rows = "".join(
                f"<tr><td>{esc(a['task'])}</td><td>{esc(a['owner']) or '—'}</td><td>{esc(a['deadline']) or '—'}</td></tr>"
                for a in minutes["action_items"]
            )
            st.markdown(
                '<div class="card"><h3>Action items</h3><table class="actions">'
                "<tr><th>Task</th><th>Owner</th><th>Deadline</th></tr>"
                f"{rows}</table></div>",
                unsafe_allow_html=True,
            )

        list_card("Open questions", minutes["open_questions"])

    with tab_tr:
        st.text_area("Full transcript", result["transcript"], height=420, label_visibility="collapsed")

    with tab_qa:
        st.markdown("Ask a question about this meeting. Answers are grounded in the transcript.")
        question = st.text_input("Your question", placeholder="What did the team decide about the launch date?")
        if st.button("Ask meeting", type="primary"):
            try:
                with st.spinner("Searching the transcript…"):
                    st.session_state["qa_answer"] = answer_question(question, result["transcript"], model=llm_model, host=config.OLLAMA_HOST)
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get("qa_answer"):
            st.markdown(st.session_state["qa_answer"])

    with tab_dl:
        base = slugify(meta["title"])
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.download_button(
            "Word (.docx)", to_docx_bytes(minutes, meta), f"{base}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
        c2.download_button(
            "Markdown (.md)", to_markdown(minutes, meta), f"{base}.md", "text/markdown",
            use_container_width=True,
        )
        c3.download_button(
            "Transcript (.txt)", result["transcript"], f"{base}-transcript.txt", "text/plain",
            use_container_width=True,
        )
        c4.download_button(
            "Data (.json)", json.dumps({"meta": meta, "minutes": minutes}, indent=2, ensure_ascii=False),
            f"{base}.json", "application/json", use_container_width=True,
        )
        c5.download_button("PDF (.pdf)", to_pdf_bytes(minutes, meta), f"{base}.pdf", "application/pdf", use_container_width=True)
        st.caption(f"A Word copy is also saved in the project's outputs folder.")

    with tab_library:
        saved = list_meetings()
        if not saved:
            st.info("No saved meetings yet. Generate minutes to add the first one.")
        else:
            for record in saved[:30]:
                saved_meta = record.get("meta", {})
                title = saved_meta.get("title") or record.get("id", "Saved meeting")
                with st.expander(f"{title} · {saved_meta.get('date', '')}"):
                    st.write((record.get("minutes") or {}).get("executive_summary", "No summary saved."))
                    st.download_button("Download saved JSON", json.dumps(record, ensure_ascii=False, indent=2), f"{slugify(title)}.json", "application/json", key=f"saved-{record.get('id')}")
