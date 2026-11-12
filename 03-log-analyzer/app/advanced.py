import re
from collections import Counter
from pathlib import Path

def validate_config(filename, text):
    ext = Path(filename).suffix.lower()
    out = []
    def finding(sev,title,desc,evidence,recs,confidence="medium"):
        return {"category":"syntax","severity":sev,"title":title,"description":desc,"evidence":evidence,"recommendations":recs,"confidence":confidence}
    if ext in {".yaml",".yml"}:
        try:
            import yaml
            yaml.safe_load(text)
            out.append(finding("info","YAML syntax valid","YAML parsed successfully; Kubernetes schema validity is not guaranteed.",["PyYAML accepted the document."],["Validate against the target Kubernetes API schema."],"high"))
        except Exception as e:
            out.append(finding("high","Invalid YAML syntax",str(e)[:500],[str(e)[:500]],["Check indentation and spaces.","Quote YAML-special values.","Run kubectl apply --dry-run=client -f <file>."],"high"))
    elif ext in {".dockerfile",".docker"} or Path(filename).name.lower()=="dockerfile":
        allowed={"FROM","RUN","CMD","LABEL","EXPOSE","ENV","ADD","COPY","ENTRYPOINT","VOLUME","USER","WORKDIR","ARG","ONBUILD","STOPSIGNAL","HEALTHCHECK","SHELL"}
        has_from=False
        for n,line in enumerate(text.splitlines(),1):
            s=line.strip()
            if not s or s.startswith("#"): continue
            token=s.split()[0].upper()
            if token not in allowed:
                out.append(finding("high","Unknown Dockerfile instruction",f"Line {n}: unknown instruction {token}.",[s[:250]],["Check instruction spelling and line continuations."],"high"))
            if token=="FROM": has_from=True
        if not has_from: out.append(finding("high","Missing FROM instruction","No base image instruction was found.",["No FROM instruction detected."],["Add a valid FROM image instruction."],"high"))
        if not out: out.append(finding("info","Dockerfile basic checks passed","No obvious instruction spelling or missing FROM issue was detected. This is not a full BuildKit validation.",["Basic static checks passed."],["Run docker build using the intended build context."],"medium"))
    elif Path(filename).name.lower() in {"jenkinsfile","jenkinsfile.groovy"} or ext==".groovy":
        stack=[]; quote=None; escaped=False; line=1; mismatch=None
        pairs={")":"(","]":"[","}":"{"}
        for ch in text:
            if ch=="\n": line+=1
            if quote:
                if escaped: escaped=False
                elif ch=="\\": escaped=True
                elif ch==quote: quote=None
                continue
            if ch in ("'","\""): quote=ch
            elif ch in "([{": stack.append((ch,line))
            elif ch in ")]}":
                if not stack or stack[-1][0]!=pairs[ch]:
                    mismatch=(ch,line); break
                stack.pop()
        if mismatch: out.append(finding("high","Unmatched Groovy delimiter",f"Unexpected {mismatch[0]} around line {mismatch[1]}.",[f"Line {mismatch[1]}"],["Check matching braces, brackets and parentheses.","Use Jenkins Pipeline Linter for full validation."]))
        elif stack: out.append(finding("high","Unclosed Groovy delimiter",f"Unclosed {stack[-1][0]} opened around line {stack[-1][1]}.",[f"Opening delimiter at line {stack[-1][1]}"],["Check matching closing delimiters.","Use Jenkins Pipeline Linter for full validation."]))
        elif quote: out.append(finding("high","Unterminated Groovy string","A quoted string was not closed.",["Unterminated quote detected."],["Check string delimiters."]))
        else: out.append(finding("info","Basic Groovy delimiter check passed","No obvious unmatched delimiters found. This is not a full Groovy compiler check.",["Lexical delimiter check passed."],["Use the Jenkins Declarative Pipeline Linter for authoritative validation."],"low"))
    return out

def detect_anomalies(logs):
    lines=logs.splitlines()
    errs=[x for x in lines if re.search(r"\b(ERROR|FATAL|CRITICAL|Exception|Traceback)\b",x,re.I)]
    counts=Counter()
    for line in errs:
        fp=re.sub(r"\b\d+\b","<n>",line.lower())
        fp=re.sub(r"\b[0-9a-f]{8,}\b","<id>",fp)
        counts[fp[:180]]+=1
    out=[]
    for fp,n in counts.most_common(5):
        if n>=3: out.append({"kind":"repeated_error","severity":"high" if n>=10 else "medium","count":n,"description":f"Repeated error signature detected {n} times.","evidence":[fp]})
    win=max(20,min(200,len(lines)//5 or 20)); buckets=[]
    for start in range(0,len(lines),win):
        chunk=lines[start:start+win]
        n=sum(bool(re.search(r"\b(ERROR|FATAL|CRITICAL|Exception|Traceback)\b",x,re.I)) for x in chunk)
        buckets.append((start+1,start+len(chunk),n))
    if len(buckets)>=2:
        avg=sum(x[2] for x in buckets[:-1])/max(1,len(buckets)-1); last=buckets[-1]
        if last[2]>=5 and last[2]>max(2,avg*3):
            out.append({"kind":"error_burst","severity":"high","count":last[2],"description":f"Error density increased in lines {last[0]}-{last[1]}.","evidence":[f"{last[2]} error-like entries in final window."]})
    return out

def correlate_events(logs):
    groups={}
    for n,line in enumerate(logs.splitlines(),1):
        if not re.search(r"error|fail|crash|restart|timeout|refused|oom|killed|unhealthy|unavailable",line,re.I): continue
        component="unknown"
        for pat in (r"pod[/=:\s]+([A-Za-z0-9_.-]+)",r"container[/=:\s]+([A-Za-z0-9_.-]+)",r"service[/=:\s]+([A-Za-z0-9_.-]+)",r"\[([A-Za-z0-9_.-]+)\]"):
            m=re.search(pat,line,re.I)
            if m: component=m.group(1); break
        groups.setdefault(component,[]).append({"line":n,"message":line.strip()[:300]})
    return [{"component":k,"event_count":len(v),"first_line":v[0]["line"],"last_line":v[-1]["line"],"events":v[:8]} for k,v in groups.items() if len(v)>1 or k!="unknown"][:20]

def extract_audit_attribution(logs):
    events=[]
    actor_patterns=[r"\buser[=:]\s*([A-Za-z0-9_.@-]+)",r"\bactor[=:]\s*([A-Za-z0-9_.@-]+)",r'\bUser\s+"([^"]+)"',r"\buid[=:]\s*(\d+)"]
    cmd=re.compile(r"(kubectl\s+[^;]+|helm\s+(?:upgrade|install|uninstall)[^;]*|terraform\s+(?:apply|destroy)[^;]*|sudo\s+[^;]+)",re.I)
    for n,line in enumerate(logs.splitlines(),1):
        m=cmd.search(line)
        if not m: continue
        actor=None
        for pat in actor_patterns:
            a=re.search(pat,line,re.I)
            if a: actor=a.group(1); break
        events.append({"line":n,"actor":actor or "not recorded","command":m.group(1)[:250],"attribution":"explicit log field" if actor else "unknown"})
    return events[:50]
