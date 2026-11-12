import io
import zipfile

from src.export import slugify, to_docx_bytes, to_markdown
from src.summarize import (
    check_ollama,
    generate_minutes,
    merge_minutes,
    normalize_minutes,
    parse_json,
    split_text,
)
from src import summarize
from src.transcribe import format_duration, format_timestamp, format_transcript

SAMPLE = {
    "title": "Q4 Planning",
    "executive_summary": "The team agreed the launch plan.",
    "participants": ["Asha", "Ravi"],
    "discussion_points": [{"topic": "Launch", "detail": "Target is mid December."}],
    "decisions": ["Launch on 15 December"],
    "action_items": [{"task": "Prepare release notes", "owner": "Ravi", "deadline": "10 Dec"}],
    "open_questions": ["Is QA capacity enough?"],
}
META = {"title": "Q4 Planning", "date": "12 November 2026", "source": "call.mp3", "duration": "", "attendees": ""}


def test_split_text_short_and_long():
    assert split_text("hello world") == ["hello world"]
    long = "\n".join(f"Sentence number {i} is here." for i in range(400))
    chunks = split_text(long, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert "Sentence number 399" in chunks[-1]


def test_split_text_single_huge_line():
    chunks = split_text("word " * 5000, max_chars=1000)
    assert all(len(c) <= 1000 for c in chunks)


def test_parse_json_variants():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here you go: {"a": 1} hope it helps') == {"a": 1}
    assert parse_json("not json") is None
    assert parse_json("") is None


def test_normalize_handles_messy_output():
    messy = {
        "summary": "Short",
        "decisions": "Only one",
        "discussion_points": ["plain string", {"topic": "T", "detail": "D"}],
        "action_items": ["Do thing", {"action": "Other", "assignee": "Sam", "due": "Friday"}],
    }
    out = normalize_minutes(messy)
    assert out["executive_summary"] == "Short"
    assert out["decisions"] == ["Only one"]
    assert out["discussion_points"][0] == {"topic": "", "detail": "plain string", "timestamp": ""}
    assert out["action_items"][1] == {"task": "Other", "owner": "Sam", "deadline": "Friday"}
    assert normalize_minutes(None)["action_items"] == []


def test_merge_dedupes():
    a = normalize_minutes(SAMPLE)
    b = normalize_minutes(SAMPLE)
    merged = merge_minutes([a, b])
    assert merged["decisions"] == ["Launch on 15 December"]
    assert len(merged["action_items"]) == 1
    assert len(merged["discussion_points"]) == 1


def test_generate_minutes_single_and_chunked(monkeypatch):
    calls = []

    def fake_chat(host, model, system, user):
        calls.append(user)
        if "exactly two keys" in user:
            return '{"title": "Merged", "executive_summary": "Overall."}'
        return '{"decisions": ["Ship it"], "action_items": [{"task": "Write docs", "owner": "A", "deadline": ""}]}'

    monkeypatch.setattr(summarize, "_chat", fake_chat)

    single = generate_minutes("This is a short meeting transcript about shipping.")
    assert single["decisions"] == ["Ship it"]
    assert len(calls) == 1

    calls.clear()
    long_text = "\n".join(f"Line {i} of a very long meeting." for i in range(1000))
    multi = generate_minutes(long_text)
    assert multi["title"] == "Merged"
    assert multi["executive_summary"] == "Overall."
    assert multi["decisions"] == ["Ship it"]
    assert len(calls) > 2


def test_generate_minutes_rejects_empty():
    try:
        generate_minutes("hi")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_check_ollama_reports_no_server(monkeypatch):
    def boom(host):
        raise ConnectionError("down")

    monkeypatch.setattr(summarize, "_client", boom)
    assert check_ollama()[0] == "no_server"


def test_check_ollama_model_listing(monkeypatch):
    class Client:
        def list(self):
            return {"models": [{"model": "llama3.2:latest"}]}

    monkeypatch.setattr(summarize, "_client", lambda host: Client())
    assert check_ollama(model="llama3.2")[0] == "ok"
    assert check_ollama(model="mistral")[0] == "no_model"


def test_markdown_export():
    md = to_markdown(normalize_minutes(SAMPLE), META)
    assert md.startswith("# Q4 Planning")
    assert "| Prepare release notes | Ravi | 10 Dec |" in md
    assert "## Decisions" in md


def test_docx_export_is_valid_zip_with_content():
    data = to_docx_bytes(normalize_minutes(SAMPLE), META)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Q4 Planning" in xml
    assert "Prepare release notes" in xml


def test_docx_export_with_empty_minutes():
    assert len(to_docx_bytes(normalize_minutes(None), {"title": "Empty"})) > 1000


def test_formatting_helpers():
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3725) == "1:02:05"
    assert format_duration(125) == "2 min 5 s"
    segs = [{"start": 0, "end": 2, "text": " Hello "}, {"start": 3, "end": 4, "text": ""}]
    assert format_transcript(segs) == "[00:00] Hello"
    assert format_transcript(segs, False) == "Hello"
    assert slugify("Q4 Planning / Kickoff!") == "q4-planning-kickoff"


def test_timestamp_in_normalized_discussion_point():
    item = normalize_minutes({"discussion_points": [{"topic": "Budget", "detail": "Reviewed", "timestamp": "03:12"}]})["discussion_points"][0]
    assert item["timestamp"] == "03:12"


def test_store_round_trip_and_delete(tmp_path, monkeypatch):
    from src import store
    monkeypatch.setattr(store, "LIBRARY_DIR", tmp_path / "meetings")
    monkeypatch.setattr(store, "AUDIO_DIR", tmp_path / "meetings" / "audio")
    path = store.save_meeting({"meta": {"title": "Demo"}, "transcript": "hello"})
    assert path.exists()
    records = store.list_meetings()
    assert records[0]["meta"]["title"] == "Demo"
    assert store.load_meeting(records[0]["id"])["transcript"] == "hello"
    assert store.delete_meeting(records[0]["id"]) is True


def test_diarization_assigns_maximum_overlap():
    from src.diarize import assign_speakers
    segments = [{"start": 1.0, "end": 3.0, "text": "hello"}]
    turns = [{"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"}, {"start": 1.5, "end": 3.5, "speaker": "SPEAKER_01"}]
    assert assign_speakers(segments, turns)[0]["speaker"] == "SPEAKER_01"
