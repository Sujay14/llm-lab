from app.advanced import validate_config, detect_anomalies, correlate_events, extract_audit_attribution

def test_yaml_invalid():
    result=validate_config("bad.yaml","items: [a, b")
    assert result and result[0]["severity"]=="high"

def test_dockerfile_missing_from():
    result=validate_config("Dockerfile","RUN echo hello")
    assert any("Missing FROM" in x["title"] for x in result)

def test_jenkinsfile_unclosed_brace():
    result=validate_config("Jenkinsfile","pipeline { stages {")
    assert any("Unclosed" in x["title"] for x in result)

def test_repeated_error_anomaly():
    result=detect_anomalies("\n".join(["ERROR database unavailable"]*4))
    assert any(x["kind"]=="repeated_error" for x in result)

def test_event_correlation():
    result=correlate_events("ERROR pod/api-1 crashed\nWARN pod/api-1 restarting")
    assert result and result[0]["component"]=="api-1"

def test_audit_actor():
    result=extract_audit_attribution("user=alice kubectl delete namespace staging")
    assert result[0]["actor"]=="alice"
