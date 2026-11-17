from .schemas import ReviewReport

ICON = {"bug": "🐞", "risk": "⚠️", "missing_test": "🧪", "style": "🎨"}

def to_markdown(r: ReviewReport) -> str:
    out = [f"## Review: {r.verdict.value.upper()}", "", r.summary, ""]
    order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(r.findings, key=lambda x: order[x.severity.value]):
        loc = f"{f.file}:{f.line}" if f.line else f.file
        flag = "" if f.verified else " _(unverified)_"
        out += [f"### {ICON[f.category.value]} [{f.severity.value}] {f.title}{flag}", f"`{loc}` — {f.category.value}", "",
                f.explanation, "", f"**Fix:** {f.suggestion}", ""]
    if not r.findings:
        out.append("_No issues found._")
    return "\n".join(out)
