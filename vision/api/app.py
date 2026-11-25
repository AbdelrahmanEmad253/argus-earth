"""Argus Earth API. Run: python -m uvicorn vision.api.app:app --host 127.0.0.1 --port 8000
Never opens DuckDB (the fetch loop owns it): reads data/search.npz only. The Groq key stays here, server-side."""
import json
import os

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from vision.search import index as ix

ROOT = ix.ROOT
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"  # fallback: llama-3.3-70b-versatile (Groq retires models; check /v1/models)

app = FastAPI(title="Argus Earth")
(ROOT / "data" / "frames").mkdir(parents=True, exist_ok=True)
app.mount("/frames", StaticFiles(directory=ROOT / "data" / "frames"), name="frames")  # only frames, never data/

_cache = {"mtime": None, "d": None}


def env(name):
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip() or None
    except FileNotFoundError:
        pass
    return None


def index():
    """Reload when the loop has swapped in a newer search.npz (read-only; one assignment, thread-safe)."""
    m = ix.INDEX.stat().st_mtime if ix.INDEX.exists() else None
    if m != _cache["mtime"]:
        _cache.update(mtime=m, d=ix.load())
    return _cache["d"]


def search(q, limit):
    """The one search path: /search and /agent both go through here, so the guardrail covers both."""
    q = q.strip()
    if not q or len(q) > 200:
        raise HTTPException(400, "query must be 1-200 characters")
    if ix.blocked(q):
        raise HTTPException(400, "Argus Earth searches scenes (weather, roads, traffic, smoke), not people or plates.")
    d = index()
    if not len(d["frame_id"]):
        return {"schema_version": 1, "query": q, "results": []}
    results = []
    for i, score in ix.rank(d["vecs"], d, ix.embed_text(q), limit * 3):
        fid = d["frame_id"][i]
        if not (ROOT / "data" / "frames" / f"{fid}.jpg").exists():  # expired after 7 days
            continue
        results.append({"camera_id": d["camera_id"][i], "name": d["name"][i], "lat": float(d["lat"][i]),
                        "lon": float(d["lon"][i]), "frame_time": d["frame_time"][i], "score": round(score, 4),
                        "image_url": f"/frames/{fid}.jpg"})
        if len(results) >= limit:
            break
    return {"schema_version": 1, "query": q, "results": results}


@app.get("/search")
def search_endpoint(q: str, limit: int = Query(10, ge=1, le=50)):
    return search(q, limit)


class AgentIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


TOOL = {"type": "function", "function": {
    "name": "search_cameras",
    "description": "Find public traffic-camera frames matching a short visual description of a scene.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "short English visual description, e.g. 'snowy road', 'fog'"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"]}}}
SYSTEM = ("You help explore live public traffic cameras on a globe. Use search_cameras for scene requests "
          "(weather, road conditions, traffic, smoke, time of day). Refuse any request about people, faces, "
          "individuals or license plates. Reply in at most two short spoken sentences, say these are the closest "
          "matches, and name the cameras.")


def fallback(text):
    try:
        s = search(text, 5)
    except HTTPException as e:
        return {"schema_version": 1, "reply": e.detail, "search": None}
    top = s["results"][0]["name"] if s["results"] else None
    reply = f"Top match: {top}, {len(s['results'])} cameras found." if top else "No matching cameras yet."
    return {"schema_version": 1, "reply": reply, "search": s}


@app.post("/agent")
def agent(body: AgentIn):
    key = env("GROQ_API_KEY")
    if not key:
        return fallback(body.text)
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": body.text}]
    hdr = {"Authorization": f"Bearer {key}"}
    try:
        r = httpx.post(GROQ_URL, headers=hdr, timeout=20,
                       json={"model": GROQ_MODEL, "messages": msgs, "tools": [TOOL], "tool_choice": "auto"})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls")
        if not calls:  # the model answered directly (e.g. a refusal)
            return {"schema_version": 1, "reply": (msg.get("content") or "").strip(), "search": None}
        args = json.loads(calls[0]["function"]["arguments"])
        try:
            s = search(str(args.get("query", "")), max(1, min(10, int(args.get("limit", 5)))))
        except HTTPException as e:
            return {"schema_version": 1, "reply": e.detail, "search": None}
        brief = [{"name": x["name"], "score": x["score"]} for x in s["results"][:5]]
        msgs += [msg, {"role": "tool", "tool_call_id": calls[0]["id"], "content": json.dumps(brief)}]
        r2 = httpx.post(GROQ_URL, headers=hdr, timeout=20, json={"model": GROQ_MODEL, "messages": msgs})
        r2.raise_for_status()
        return {"schema_version": 1, "reply": r2.json()["choices"][0]["message"]["content"].strip(), "search": s}
    except Exception:  # no key, rate limit, retired model, tool_use_failed...: plain search still works
        return fallback(body.text)
