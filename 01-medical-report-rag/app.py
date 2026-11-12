"""Medical Report Assistant: Streamlit interface. Run with:  streamlit run app.py"""
import logging

import streamlit as st

import config
from services.llm_service import build_messages, stream_answer
from services.ollama_client import check_ollama
from services.rag_pipeline import ingest_report, retrieve
from utils.errors import UserFacingError
from utils.prompt_templates import DISCLAIMER, NO_MATCH_SOURCES, NO_RESULTS_MESSAGE, format_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # keep request noise out of the terminal
log = logging.getLogger("app")

SUGGESTED_QUESTIONS = [
    "Summarize this report in simple English.",
    "Which results are marked outside the reference range?",
    "Explain the cholesterol results in this report.",
    "What does HbA1c mean?",
    "Explain the Vitamin B12 result.",
    "What do the thyroid test results say?",
    "Which page contains the lipid profile?",
]

st.set_page_config(page_title="Medical Report Assistant", page_icon="🩺", layout="centered")

# ------------------------------------------------------------------ session state
for key, default in {
    "report": None,          # IngestResult for the active report (holds its own ChromaDB collection)
    "messages": [],          # chat history shown on screen
    "uploader_key": 0,       # changing it empties the file uploader
    "ollama_status": None,
}.items():
    st.session_state.setdefault(key, default)


def reset_report() -> None:
    """Forget the current report completely: delete its vectors, clear the chat, empty the uploader."""
    if st.session_state.report is not None:
        st.session_state.report.store.close()
    st.session_state.report = None
    st.session_state.messages = []
    st.session_state.uploader_key += 1


def llm_history() -> list[dict]:
    """Previous successful question/answer pairs, in the form the model needs (no sources/disclaimer)."""
    history: list[dict] = []
    msgs = st.session_state.messages
    for user, assistant in zip(msgs[::2], msgs[1::2]):
        if assistant.get("body"):
            history += [{"role": "user", "content": user["content"]}, {"role": "assistant", "content": assistant["body"]}]
    return history


def render_message(msg: dict) -> None:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        elif msg.get("error"):
            st.error(msg["error"])
        else:
            st.markdown(msg["body"])
            st.markdown(msg["footer"])
            if msg.get("debug"):
                with st.expander("Retrieved excerpts (developer view)"):
                    st.text(msg["debug"])


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("About")
    st.markdown(f"**Answer model:** `{config.LLM_MODEL}`  \n**Embedding model:** `{config.EMBED_MODEL}`")
    status = st.session_state.ollama_status
    if status is None or not status.ok or st.button("Re-check Ollama"):
        status = st.session_state.ollama_status = check_ollama()
    if status.ok:
        st.success("Ollama is running and both models are installed.")
    elif not status.running:
        st.error("Ollama is not running. Install it from https://ollama.com/download/windows and start it.")
    else:
        st.error("Missing model(s). In PowerShell run:")
        st.code("\n".join(f"ollama pull {m}" for m in status.missing_models), language="powershell")

    st.header("How to use")
    st.markdown(
        "1. Upload a text-based lab report PDF.\n"
        "2. Click **Process report**.\n"
        "3. Ask questions in plain language.\n"
        "4. Ask follow-ups; no need to upload again."
    )
    st.header("Privacy")
    st.caption(
        "Everything runs on this computer. The report is kept in memory only and disappears when "
        "the app restarts or you upload another report. Patient name and ID fields are removed "
        "before indexing (best effort)."
    )
    show_debug = st.checkbox("Developer view: show retrieved excerpts", value=False)

# ------------------------------------------------------------------ header
st.title("Medical Report Assistant")
st.subheader("Understand your medical reports with AI.")
st.warning(
    "**Educational use only.** This tool explains what is written in your report. It is not a doctor, "
    "does not diagnose, and does not give treatment advice. Talk to a qualified healthcare "
    "professional about your results."
)

# ------------------------------------------------------------------ step 1: upload and process
if st.session_state.report is None:
    uploaded = st.file_uploader("Upload your lab report (PDF)", type=["pdf"], key=f"uploader_{st.session_state.uploader_key}")
    if st.button("Process report", type="primary", disabled=uploaded is None):
        if not status.ok:
            st.error("Ollama is not ready yet. See the sidebar for what to fix, then try again.")
        else:
            bar = st.progress(0.0, text="Starting…")
            try:
                st.session_state.report = ingest_report(
                    uploaded.getvalue(), status=lambda msg, frac: bar.progress(min(frac, 1.0), text=msg)
                )
                st.session_state.messages = []
                st.rerun()
            except UserFacingError as err:
                bar.empty()
                st.error(str(err))
            except Exception:  # noqa: BLE001 - never show a traceback to the user
                log.exception("Unexpected error while processing the report")
                bar.empty()
                st.error("Something went wrong while processing the report. Details are in the terminal window.")
    st.stop()

# ------------------------------------------------------------------ step 2: chat
report = st.session_state.report
st.success("Report processed. You can now ask questions.")
c1, c2, c3 = st.columns(3)
c1.metric("Pages", report.page_count)
c2.metric("Chunks indexed", report.chunk_count)
c3.metric("Pages with text", report.pages_with_text)
if report.pages_without_text:
    st.caption(f"PDF pages with no readable content (blank, header-only or image-only): {report.pages_without_text}")
if st.button("Upload another report"):
    reset_report()
    st.rerun()

clicked = None
with st.expander("Suggested questions", expanded=not st.session_state.messages):
    for i, q in enumerate(SUGGESTED_QUESTIONS):
        if st.button(q, key=f"suggest_{i}"):
            clicked = q

for msg in st.session_state.messages:
    render_message(msg)

question = st.chat_input("Ask about your report, e.g. “Explain my cholesterol results”") or clicked
if question:
    history = llm_history()
    previous = history[-2]["content"] if len(history) >= 2 else None
    st.session_state.messages.append({"role": "user", "content": question})
    render_message(st.session_state.messages[-1])
    answer: dict = {"role": "assistant"}
    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching your report…"):
                found = retrieve(report.store, question, previous)
            if not found.items:
                answer.update(body=NO_RESULTS_MESSAGE, footer=DISCLAIMER)
                st.markdown(NO_RESULTS_MESSAGE)
            else:
                holder = st.empty()
                holder.info("Llama is thinking... the first words can take a minute on a PC without a GPU.")

                def tokens():
                    first = True
                    for piece in stream_answer(build_messages(question, found.items, history, found.weak)):
                        if first:
                            holder.empty()
                            first = False
                        yield piece

                try:
                    body = st.write_stream(tokens())
                finally:
                    holder.empty()
                sources = NO_MATCH_SOURCES if found.weak else format_sources(found.items)
                footer = f"**Source page(s):** {sources}\n\n{DISCLAIMER}"
                st.markdown(footer)
                answer.update(body=body, footer=footer)
                if show_debug:
                    answer["debug"] = "\n\n".join(
                        f"[PDF page {r.pdf_page} | distance {r.distance:.3f}]\n{r.text}" for r in found.items
                    )
        except UserFacingError as err:
            answer["error"] = str(err)
            st.error(str(err))
        except Exception:  # noqa: BLE001
            log.exception("Unexpected error while answering")
            answer["error"] = "Something went wrong while answering. Details are in the terminal window."
            st.error(answer["error"])
    st.session_state.messages.append(answer)
    if answer.get("debug"):
        st.rerun()  # re-render so the developer expander appears

st.caption("Educational prototype. Not a medical device. Not a substitute for professional advice.")
