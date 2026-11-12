import re
LEVEL=re.compile(r"\b(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b",re.I)
TIME=re.compile(r"(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d|\d\d:\d\d:\d\d)")
RULES=[
(r"CrashLoopBackOff|Back-off restarting failed container","Kubernetes","high","Pod restart loop","Container repeatedly fails and Kubernetes backs off restarts.",["kubectl describe pod <pod>","kubectl logs <pod> --previous","Inspect startup and liveness probes"]),
(r"ImagePullBackOff|ErrImagePull","Kubernetes","high","Image pull failure","Kubernetes cannot pull the configured container image.",["Verify image name and tag","Check registry access and imagePullSecrets"]),
(r"OOMKilled|out of memory|memory cgroup out of memory","Resources","critical","Memory exhaustion","A process or container appears to have been killed due to memory pressure.",["Inspect memory usage and limits","Check for leaks or workload spikes"]),
(r"liveness probe failed|readiness probe failed","Kubernetes","high","Health probe failure","A configured Kubernetes health probe is failing.",["Check probe path, port and thresholds","Inspect application startup and health endpoint"]),
(r"FailedScheduling|Insufficient cpu|Insufficient memory","Kubernetes","high","Pod scheduling failure","The scheduler cannot place the pod due to capacity or scheduling constraints.",["Inspect pod events","Check node capacity, taints and resource requests"]),
(r"permission denied|operation not permitted|EACCES","Permissions","high","Permission failure","An operation was rejected due to insufficient permissions.",["Check runtime user and group","Inspect file permissions and securityContext"]),
(r"connection refused|ECONNREFUSED","Network","high","Connection refused","The destination did not accept the connection.",["Verify service and port","Check listener, endpoints and firewall"]),
(r"timed out|ETIMEDOUT","Network","medium","Request timeout","An operation exceeded its timeout.",["Check downstream health and latency","Inspect DNS and network policy"]),
(r"could not resolve host|name or service not known","Network","high","DNS resolution failure","A hostname could not be resolved.",["Check DNS configuration","Verify service name and namespace"]),
(r"no space left on device|disk quota exceeded","Linux","critical","Disk capacity exhausted","The filesystem has insufficient free space.",["Check df -h and df -i","Identify growth using approved retention procedures"]),
(r"upstream prematurely closed|no live upstreams","Nginx","high","Nginx upstream failure","Nginx cannot communicate successfully with an upstream.",["Check upstream health and port","Verify proxy_pass and DNS"]),
(r"syntax error|mapping values are not allowed|unexpected token","Configuration","high","Possible syntax error","The log suggests malformed configuration or invalid syntax.",["Validate with the native parser","Inspect recent config changes"]),
]
def analyze(logs,filename):
 lines=logs.splitlines(); levels={}
 for line in lines:
  m=LEVEL.search(line)
  if m:
   k=m.group(1).upper().replace("WARNING","WARN"); levels[k]=levels.get(k,0)+1
 low=(filename+"\n"+logs[:10000]).lower()
 source=next((s for key,s in [("kubernetes","kubernetes"),("kubectl","kubernetes"),("crashloopbackoff","kubernetes"),("imagepullbackoff","kubernetes"),("pod/","kubernetes"),("back-off restarting failed container","kubernetes"),("oomkilled","kubernetes"),("nginx","nginx"),("jenkins","jenkins"),("docker","docker"),("systemd","linux")] if key in low),"application")
 findings=[]
 for pat,cat,sev,title,desc,fix in RULES:
  hits=[x.strip()[:350] for x in lines if re.search(pat,x,re.I)]
  if hits: findings.append(dict(category=cat,severity=sev,title=title,description=desc,evidence=hits[:8],recommendations=fix,confidence="high" if len(hits)>1 else "medium"))
 destructive=[x.strip() for x in lines if re.search(r"kubectl\s+delete\s+namespace|kubectl\s+delete\s+--all|helm\s+uninstall|terraform\s+destroy|sudo\s+rm\s+-rf",x,re.I)]
 if destructive: findings.append(dict(category="change-risk",severity="critical",title="Potential destructive command",description="A destructive command pattern appears in the text. This does not prove who ran it or that it caused the incident.",evidence=destructive[:8],recommendations=["Correlate with authoritative audit logs and actor identity","Compare timestamps with the outage"],confidence="medium"))
 timeline=[]
 for i,line in enumerate(lines,1):
  m=TIME.search(line)
  if m: timeline.append({"line":i,"timestamp":m.group(1),"message":line[:400]})
 errors=sum(v for k,v in levels.items() if k in ("ERROR","FATAL","CRITICAL"))
 return dict(source_type=source,total_lines=len(lines),error_count=errors,warning_count=levels.get("WARN",0),findings=findings,timeline=timeline[:100],summary=f"Processed {len(lines)} lines; {errors} error-level entries and {levels.get('WARN',0)} warnings; {len(findings)} finding(s).")

from app.advanced import detect_anomalies, correlate_events, extract_audit_attribution
def enrich(logs, result):
    result["anomalies"] = detect_anomalies(logs)
    result["correlations"] = correlate_events(logs)
    result["audit_events"] = extract_audit_attribution(logs)
    return result
