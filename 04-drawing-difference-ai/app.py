"""Streamlit UI:  streamlit run app.py"""
import os
import tempfile

import streamlit as st

from drawing_diff import CompareOptions, compare_pdfs, write_outputs

st.set_page_config(page_title="Drawing / PDF Compare AI", layout="wide")
st.title("Drawing / PDF Compare AI")
st.caption("Pixel + text diff finds the changes; an optional LLM explains them.")

with st.sidebar:
    st.header("Settings")
    domain = st.selectbox("Domain", ["tekla", "medical", "generic"],
                          help="tekla = structural drawings, medical = lab/prescription text, generic = anything")
    backend = st.selectbox("LLM backend", ["none", "ollama", "anthropic"],
                           help="none = rule-based only (fast, free). ollama = local. anthropic = needs ANTHROPIC_API_KEY.")
    model = st.text_input("Model (optional)", value="llama3.2-vision" if backend == "ollama" else
                          "claude-sonnet-5-5" if backend == "anthropic" else "")
    host = st.text_input("Ollama host", "http://localhost:11434") if backend == "ollama" else "http://localhost:11434"
    llm_text = st.checkbox("LLM also explains text changes", value=False, disabled=backend == "none")
    vis_choice = st.selectbox("Visual (pixel) diff", ["domain default", "on", "off"])
    dpi = st.slider("Render DPI", 100, 300, 200, 25)
    match_by = st.selectbox("Match sheets by", ["auto", "index"])
    ocr = st.checkbox("OCR scanned PDFs (needs Tesseract)", value=False)
    if domain == "medical":
        st.warning("Change highlighter only - not a clinical decision tool. Prefer a local LLM (ollama) for patient data.")

c1, c2 = st.columns(2)
fa = c1.file_uploader("Revision A (old)", type="pdf")
fb = c2.file_uploader("Revision B (new)", type="pdf")

if st.button("Compare", type="primary", disabled=not (fa and fb)):
    out_dir = tempfile.mkdtemp(prefix="pdfdiff_")
    opts = CompareOptions(domain=domain, dpi=dpi, backend=backend, model=model or None, ollama_host=host,
                          llm_text=llm_text, ocr=ocr, match_by=match_by, out_dir=out_dir,
                          visual=None if vis_choice == "domain default" else vis_choice == "on")
    bar = st.progress(0.0, text="Starting...")

    def prog(msg, frac=None):
        bar.progress(min(1.0, frac or 0.0), text=msg)

    try:
        res = compare_pdfs(fa.getvalue(), fb.getvalue(), opts, progress=prog)
        res["meta"]["file_a"], res["meta"]["file_b"] = fa.name, fb.name
        paths = write_outputs(res, out_dir)
        st.session_state["res"], st.session_state["paths"], st.session_state["dir"] = res, paths, out_dir
    except Exception as ex:
        st.error(f"Comparison failed: {ex}")
    bar.empty()

res = st.session_state.get("res")
if res:
    m, stt = res["meta"], res["stats"]
    st.subheader("Summary")
    st.write(res["summary"])
    if m.get("disclaimer"):
        st.info(m["disclaimer"])
    k = st.columns(4)
    k[0].metric("Total changes", stt["total"])
    for col, s in zip(k[1:], ("high", "medium", "low")):
        col.metric(s.capitalize(), stt["by_severity"].get(s, 0))

    d1, d2, d3 = st.columns(3)
    for col, key, label, mime in ((d1, "html", "Download HTML report", "text/html"),
                                  (d2, "json", "Download JSON", "application/json"),
                                  (d3, "csv", "Download CSV", "text/csv")):
        with open(st.session_state["paths"][key], "rb") as f:
            col.download_button(label, f.read(), file_name=os.path.basename(st.session_state["paths"][key]), mime=mime)

    sev_filter = st.multiselect("Show severities", ["high", "medium", "low"], default=["high", "medium", "low"])
    for p in res["pages"]:
        chs = [c for c in res["changes"] if c["page"] == p["label"] and c["severity"] in sev_filter]
        with st.expander(f"Sheet {p['label']} - {p['n_changes']} change(s)", expanded=bool(chs)):
            for line in p["entity_summary"]:
                st.markdown(f"- {line}")
            if p.get("overlay"):
                st.image(os.path.join(st.session_state["dir"], p["overlay"]),
                         caption="Overlay: red = only in A, green = only in B")
            for c in chs:
                icon = {"high": "🔴", "medium": "🟠", "low": "⚪"}[c["severity"]]
                st.markdown(f"**{icon} {c['id']} - {c['change_type']}** ({c['source']}"
                            f"{' + LLM' if c.get('llm_used') else ''}, conf {c['confidence']:.2f})  \n{c['description']}")
                if c.get("old") or c.get("new"):
                    st.code(f"{c.get('old') or '-'}  ->  {c.get('new') or '-'}", language=None)
                if c.get("image"):
                    st.image(os.path.join(st.session_state["dir"], c["image"]))
