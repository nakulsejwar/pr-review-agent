"""Tiny web demo: paste a diff, get the review.  `uvicorn app:app --reload`"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from reviewer.agent import ReviewAgent
from reviewer.render import to_markdown

app = FastAPI(title="Diff Review Agent")

class Req(BaseModel):
    diff: str

PAGE = """<!doctype html><meta charset=utf-8><title>Diff Review Agent</title>
<style>body{font:15px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}textarea{width:100%;height:260px;font:12px monospace}
button{padding:.6rem 1.2rem;font-size:1rem}pre{white-space:pre-wrap;background:#f5f5f5;padding:1rem;border-radius:6px}</style>
<h2>Diff Review Agent (Gemini)</h2><textarea id=d placeholder="Paste a unified diff / git diff here"></textarea><br>
<button onclick=go()>Review</button><pre id=o></pre>
<script>async function go(){o.textContent='Reviewing...';const r=await fetch('/review',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({diff:d.value})});
const j=await r.json();o.textContent=r.ok?j.markdown:('Error: '+j.detail)}</script>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE

@app.post("/review")
def review(req: Req):
    if len(req.diff) > 200_000:
        raise HTTPException(413, "Diff too large")
    try:
        agent = ReviewAgent()
        rep = agent.review(req.diff)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Review failed: {type(e).__name__}")
    return {"markdown": to_markdown(rep), "report": rep.model_dump(), "trace": agent.trace}
