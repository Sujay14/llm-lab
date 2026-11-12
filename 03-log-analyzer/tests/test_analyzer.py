from app.analyzer import analyze
def test_crashloop_detected():
 d=analyze("ERROR Back-off restarting failed container","pod.log")
 assert d["source_type"]=="kubernetes"
 assert d["findings"][0]["title"]=="Pod restart loop"
def test_no_human_error_assumption():
 d=analyze("ERROR deployment timed out","app.log")
 assert not any(x["category"]=="change-risk" for x in d["findings"])
def test_destructive_command_flagged_as_potential():
 d=analyze("kubectl delete namespace production","audit.log")
 assert any("does not prove" in x["description"] for x in d["findings"])
