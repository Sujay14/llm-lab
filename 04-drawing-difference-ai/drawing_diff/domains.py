"""Domain layers: rule-based classification of changes + page entity summaries.

Add your own domain by subclassing Domain and registering it in DOMAINS.
"""
from __future__ import annotations

import re
from collections import Counter

from .extract import group_lines

NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def nums(s: str):
    return [float(x.replace(",", ".")) for x in NUM_RE.findall(s or "")]


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _res(ctype, desc, sev, old, new, conf=1.0):
    return dict(change_type=ctype, description=desc, severity=sev, old=old or None, new=new or None, confidence=conf)


class Domain:
    name = "generic"
    label = "technical document"
    granularity = "word"      # 'word' or 'line' text diff
    visual = True             # run pixel diff by default
    change_types = ["text", "value", "added_element", "removed_element", "modified_element", "other"]
    hint = ""
    disclaimer = ""

    def classify(self, old: str, new: str) -> dict:
        o, n = (old or "").strip(), (new or "").strip()
        if o and n:
            a, b = nums(o), nums(n)
            if len(a) == 1 and len(b) == 1 and not re.search(r"[A-Za-z]{3,}", o + n):
                return _res("value", f"Value changed from {o} to {n}", "medium", o, n)
            return _res("text", f"Text changed from '{o}' to '{n}'", "medium", o, n)
        if n:
            return _res("added_text", f"Text added: '{n}'", "low", None, n)
        return _res("removed_text", f"Text removed: '{o}'", "low", o, None)

    def page_summary(self, words_a, words_b) -> list[str]:
        return []


# ------------------------------------------------------------------- Tekla
PROFILE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:HE[ABM]|IPE|IPN|UPN|UPE|UB|UC|PFC|RHS|SHS|CHS|HSS|PL|FL|FB)\s?\d+(?:[xX×*]\d+(?:\.\d+)?){0,2}(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])L\s?\d+[xX×*]\d+(?:[xX×*]\d+)?(?![A-Za-z0-9])"
)
BOLT_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+\s?[xX×]\s?)?M\d{1,2}(?:\s?[xX×]\s?\d{2,3})?(?:\s?(?:8\.8|10\.9|4\.6|12\.9))?(?![A-Za-z0-9])"
)
WELD_RE = re.compile(r"(?<![A-Za-z0-9])(?:FW|BW|CJP|PJP)\s?\d*(?![A-Za-z0-9])|(?<![A-Za-z0-9])a\d{1,2}(?![A-Za-z0-9])|fillet", re.I)
MARK_RE = re.compile(r"[A-Z]{1,3}[-_]?\d{1,4}[A-Z]?")
DIM_RE = re.compile(r"\d{3,5}")


def _norm(s: str) -> str:
    return s.upper().replace(" ", "").replace("×", "X").replace("*", "X")


class TeklaDomain(Domain):
    name = "tekla"
    label = "structural steel (Tekla) drawing"
    granularity = "word"
    visual = True
    change_types = ["dimension", "member_size", "bolt", "weld", "mark", "note",
                    "added_element", "removed_element", "modified_element", "other"]
    hint = ("Pay attention to dimensions (mm), member profiles (HEA/IPE/PL/L...), bolt callouts "
            "(e.g. 4xM20), weld symbols, member marks, and revision notes.")

    @staticmethod
    def _kind(s: str) -> str:
        s = s.strip()
        if BOLT_RE.search(s):
            return "bolt"
        if PROFILE_RE.search(s):
            return "member_size"
        if WELD_RE.search(s):
            return "weld"
        if re.fullmatch(r"[^A-Za-z]*\d[^A-Za-z]*|[A-Za-z]{1,2}\s?[=:]\s?\d+(?:[.,]\d+)?\s?(?:mm)?", s):
            return "dimension"
        if MARK_RE.fullmatch(s):
            return "mark"
        if len(re.findall(r"[A-Za-z]{3,}", s)) >= 2:
            return "note"
        return "text"

    def classify(self, old, new):
        o, n = (old or "").strip(), (new or "").strip()
        ko = self._kind(o) if o else None
        kn = self._kind(n) if n else None
        high = {"member_size", "bolt", "weld", "dimension"}
        if o and n:
            kind = kn if ko == kn else (kn if kn != "text" else ko)
            sev = "high" if kind in high else "medium" if kind in ("mark", "note") else "low"
            if kind == "dimension":
                a, b = nums(o), nums(n)
                if len(a) == 1 and len(b) == 1:
                    d = b[0] - a[0]
                    return _res("dimension", f"Dimension changed from {_fmt(a[0])} to {_fmt(b[0])} ({d:+g})", "high", o, n)
            label = {"member_size": "Member profile", "bolt": "Bolt callout", "weld": "Weld",
                     "dimension": "Dimension", "mark": "Member mark", "note": "Note"}.get(kind, "Text")
            return _res(kind if kind != "text" else "other", f"{label} changed from '{o}' to '{n}'", sev, o, n)
        if n:
            kind = kn
            sev = "high" if kind in ("member_size", "bolt", "weld") else "medium" if kind in ("dimension", "mark", "note") else "low"
            return _res(kind if kind != "text" else "added_element", f"Added {kind}: '{n}'", sev, None, n)
        kind = ko
        sev = "high" if kind in ("member_size", "bolt", "weld") else "medium" if kind in ("dimension", "mark", "note") else "low"
        return _res(kind if kind != "text" else "removed_element", f"Removed {kind}: '{o}'", sev, o, None)

    def _entities(self, words):
        text = " ".join(w.text for w in words)
        prof = Counter(_norm(m.group(0)) for m in PROFILE_RE.finditer(text))
        bolt = Counter(_norm(m.group(0)) for m in BOLT_RE.finditer(text))
        marks, dims = Counter(), Counter()
        for w in words:
            t = w.text.strip(".,;:()")
            if MARK_RE.fullmatch(t) and not PROFILE_RE.fullmatch(t) and not BOLT_RE.fullmatch(t):
                marks[t] += 1
            elif DIM_RE.fullmatch(t):
                dims[t] += 1
        return prof, bolt, marks, dims

    def page_summary(self, words_a, words_b):
        pa, ba, ma, da = self._entities(words_a)
        pb, bb, mb, db = self._entities(words_b)
        out = []
        for title, ca, cb in (("Profile", pa, pb), ("Bolt spec", ba, bb)):
            for k in sorted(set(ca) | set(cb)):
                if ca[k] != cb[k]:
                    out.append(f"{title} {k}: {ca[k]} -> {cb[k]} occurrence(s)")
        added, removed = sorted(set(mb) - set(ma)), sorted(set(ma) - set(mb))
        if removed:
            out.append("Marks removed: " + ", ".join(removed))
        if added:
            out.append("Marks added: " + ", ".join(added))
        rd, ad = da - db, db - da
        if rd or ad:
            out.append("Dimensions removed: " + (", ".join(sorted(rd.elements())) or "-")
                       + " | added: " + (", ".join(sorted(ad.elements())) or "-"))
        return out


# ----------------------------------------------------------------- Medical
LAB_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()/%,.\-]*?)\s*[:\s]\s*(?P<flag>[<>]?)(?P<value>\d+(?:[.,]\d+)?)(?=\s|$)"
    r"\s*(?P<unit>[A-Za-zµ%][A-Za-z0-9µ%/^*.\-]*)?"
    r"(?:\s+(?P<lo>\d+(?:[.,]\d+)?)\s*[-–]\s*(?P<hi>\d+(?:[.,]\d+)?))?"
)
MED_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z\-]+(?: [A-Za-z\-]+)?)\s+(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>mg|mcg|µg|g|ml|mL|IU|units?)(?![/\w])(?P<rest>.*)$"
)
DATE_RE = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b")


def _f(x):
    return float(x.replace(",", ".")) if x else None


def parse_row(line: str):
    line = line.strip()
    m = MED_RE.match(line)
    if m:
        return dict(kind="med", name=m["name"].strip().lower(), value=_f(m["value"]), unit=m["unit"].lower(),
                    rest=m["rest"].strip(), lo=None, hi=None, raw=line)
    m = LAB_RE.match(line)
    if m:
        return dict(kind="lab", name=m["name"].strip().lower(), value=_f(m["value"]), unit=(m["unit"] or "").strip(),
                    rest="", lo=_f(m["lo"]), hi=_f(m["hi"]), raw=line)
    return None


class MedicalDomain(Domain):
    name = "medical"
    label = "medical document (lab report / prescription / clinical note)"
    granularity = "line"
    visual = False  # text/table documents: the line diff is the signal
    change_types = ["lab_value", "medication", "date", "added_row", "removed_row", "note", "other"]
    hint = "Focus on lab values and units, reference ranges, medication names/doses/frequency, and dates."
    disclaimer = ("This tool highlights differences between two documents. It is NOT a clinical decision "
                  "tool; a qualified professional must review every change.")

    @staticmethod
    def _out(row, lo=None, hi=None):
        lo = row["lo"] if row and row["lo"] is not None else lo
        hi = row["hi"] if row and row["hi"] is not None else hi
        if row is None or row["value"] is None or lo is None or hi is None:
            return None
        return row["value"] < lo or row["value"] > hi

    def classify(self, old, new):
        o, n = (old or "").strip(), (new or "").strip()
        ro, rn = (parse_row(o) if o else None), (parse_row(n) if n else None)
        if ro and rn and ro["name"] == rn["name"] and ro["kind"] == rn["kind"]:
            name = rn["name"].title()
            if rn["kind"] == "med":
                if ro["value"] != rn["value"] or ro["unit"] != rn["unit"]:
                    return _res("medication", f"{name} dose changed from {_fmt(ro['value'])} {ro['unit']} to "
                                f"{_fmt(rn['value'])} {rn['unit']}", "high", o, n, 0.95)
                if ro["rest"] != rn["rest"]:
                    return _res("medication", f"{name} instructions changed: '{ro['rest']}' -> '{rn['rest']}'", "high", o, n, 0.9)
            else:
                if ro["value"] != rn["value"] or ro["unit"] != rn["unit"]:
                    pct = ((rn["value"] - ro["value"]) / ro["value"] * 100) if ro["value"] else None
                    oo, on = self._out(ro), self._out(rn, ro["lo"], ro["hi"])
                    sev = "low"
                    if ro["unit"] != rn["unit"]:
                        sev = "high"
                    elif on and not oo:
                        sev = "high"
                    elif pct is not None and abs(pct) >= 20:
                        sev = "high"
                    elif pct is not None and abs(pct) >= 5:
                        sev = "medium"
                    extra = f" ({pct:+.1f}%)" if pct is not None else ""
                    flag = " [now outside reference range]" if (on and not oo) else " [back within range]" if (oo and on is False) else ""
                    return _res("lab_value", f"{name}: {_fmt(ro['value'])} {ro['unit']} -> {_fmt(rn['value'])} {rn['unit']}{extra}{flag}",
                                sev, o, n, 0.95)
                return _res("lab_value", f"{name}: reference range / flags changed ('{o}' -> '{n}')", "low", o, n, 0.8)
        if o and n:
            if DATE_RE.findall(o) != DATE_RE.findall(n):
                return _res("date", f"Date changed: '{o}' -> '{n}'", "medium", o, n, 0.85)
            return _res("note", f"Text changed: '{o}' -> '{n}'", "medium", o, n, 0.8)
        if n:
            if rn:
                t = "medication" if rn["kind"] == "med" else "added_row"
                return _res(t, f"Added {rn['kind']}: {n}", "high" if rn["kind"] == "med" else "medium", None, n, 0.9)
            return _res("note", f"Text added: '{n}'", "medium", None, n, 0.8)
        if ro:
            t = "medication" if ro["kind"] == "med" else "removed_row"
            return _res(t, f"Removed {ro['kind']}: {o}", "high" if ro["kind"] == "med" else "medium", o, None, 0.9)
        return _res("note", f"Text removed: '{o}'", "medium", o, None, 0.8)


DOMAINS = {"generic": Domain, "tekla": TeklaDomain, "medical": MedicalDomain}


def get_domain(name: str) -> Domain:
    return DOMAINS.get((name or "generic").lower(), Domain)()
