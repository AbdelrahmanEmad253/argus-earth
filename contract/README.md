# Data contract (DRAFT v1: review before building on it)

Both sides code against this folder. Python writes these formats, the JavaScript globe layers read them.
Nobody changes a format without telling the other person and updating `contract/`.

## Rules for all formats
- Times: UTC, ISO 8601 text, e.g. `2026-11-23T14:05:00Z`.
- Coordinates: `lat`, `lon` in decimal degrees (WGS84).
- Camera id: `<source>_<id from the source>`, e.g. `caltrans_d7_i110196avenue26offramp`, `austin_456`, `tfl_00001.06514`.
- Names are lowercase with underscores.
- Not computed yet = `null`. A count of zero = `0`. They mean different things.
- Every JSON file has `"schema_version": 1` at the top. Increase it when a format changes.

## Database: `data/vision.duckdb`
Tables are defined in [`schema.sql`](schema.sql), the only copy. Timestamps are stored as naive UTC and get the `Z` on export.

`results.value_json` per feature:

| feature | owner | value_json |
|---|---|---|
| `density` | Rowaina | `{"car": 12, "truck": 3, "bus": 1, "motorcycle": 0, "total": 16}` |
| `weather` | Abdelrahman | `{"label": "fog", "score": 0.81}` (labels: clear, rain, snow, fog, wet_road, unknown) |
| `people_bikes` | Rowaina | `{"person": 4, "bicycle": 1}` |
| `smoke` | Abdelrahman | `{"smoke": true, "score": 0.74}` |

## Snapshot: `web/public/vision/latest.json`
Written by `python -m vision.store.export`. Schema: [`latest.schema.json`](latest.schema.json). Example: [`examples/latest.json`](examples/latest.json).
Each globe layer reads only this file; build against the example before the model exists.

## Not yet defined (owners agree the format before building)
`timeline/<camera_id>.json` (patterns), `fire_checks.json`, `ship_detections.json`.

## Extra files (not in the original plan)
- `data/ais.duckdb`: table `ais(mmsi, t, lat, lon, sog, cog, name)`, English Channel ship positions, written by `vision/fetch/ais.py`. Separate file because DuckDB allows one writer per file on Windows.

## Search API (DRAFT: changes vs the original plan, please review)
`python -m uvicorn vision.api.app:app --host 127.0.0.1 --port 8000`. The browser reaches it at `/argus/*` (Vite proxy).
- `GET /search?q=snowy%20road&limit=10`: see [`examples/search.json`](examples/search.json). Adds a `name` field (readable camera name) to the planned format. One best frame per camera. Person, face and plate queries return 400.
- `POST /agent {"text": "..."}` returns `{"schema_version": 1, "reply": "...", "search": <search response>|null}`. Groq tool-calling, key kept server-side; without a key it falls back to a plain search.
- Index: `data/search.npz` (CLIP ViT-B-32 vectors plus camera metadata in one file) replaces the planned `search.index` + `search_ids.json`. Brute-force cosine; swap to FAISS if the data grows past about 100k frames.
- Privacy: only camera-level scene search. Chrome and Edge send microphone audio to their own cloud speech service; Groq receives the spoken text and camera names, never images.
