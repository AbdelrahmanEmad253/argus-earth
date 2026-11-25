"""Search by description: CLIP embeddings of camera frames in one data/search.npz, numpy cosine ranking.
Scene-level search of open-data traffic cameras only. Person/face/plate queries are refused (see blocked()).
Run: python -m vision.search.index --selftest | --limit N | --query "snowy road"
# ponytail: brute-force dot product with a full file rewrite each cycle; fine to ~100k vectors,
# move to FAISS (PLAN) or per-day files above ~1M."""
import argparse
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "search.npz"
MODEL, PRETRAINED = "ViT-B-32", "laion2b_s34b_b79k"
PROMPT = "a traffic camera photo of {}"  # tune: scores are uncalibrated, search always returns something
FIELDS = ("frame_id", "camera_id", "name", "lat", "lon", "frame_time")
_m = None

BLOCKED = re.compile(
    r"\b(person|people|man|men|woman|women|guy|kid|kids|child|children|boy|girl|face|faces|someone|somebody|"
    r"wearing|jacket|shirt|driver|passenger|pedestrians?|cyclists?|plates?|licen[cs]e|named)\b", re.I)


def blocked(q):
    """Guardrail (best effort): no person search. Camera-level results are the real protection."""
    return bool(BLOCKED.search(q))


def _model():
    global _m
    if _m is None:
        import open_clip
        import torch
        cache = ROOT / "data" / "models"
        cache.mkdir(parents=True, exist_ok=True)
        model, _, pre = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, cache_dir=str(cache))
        _m = (model.eval(), pre, open_clip.get_tokenizer(MODEL), torch)
    return _m


def embed_images(paths, batch=32):
    from PIL import Image
    model, pre, _, torch = _model()
    out, keep = [], []
    for i in range(0, len(paths), batch):
        ims, ok = [], []
        for j, p in enumerate(paths[i:i + batch]):
            try:
                ims.append(pre(Image.open(p).convert("RGB")))
                ok.append(i + j)
            except Exception:  # missing or corrupt frame: skip, never crash the loop
                pass
        if ims:
            with torch.inference_mode():
                v = model.encode_image(torch.stack(ims))
            out.append((v / v.norm(dim=-1, keepdim=True)).numpy())
            keep += ok
    return (np.concatenate(out) if out else np.zeros((0, 512), np.float32)), keep


def embed_text(q):
    model, _, tok, torch = _model()
    with torch.inference_mode():
        v = model.encode_text(tok([PROMPT.format(q)]))
    return (v / v.norm(dim=-1, keepdim=True)).numpy()[0]


def load():
    """Copy everything out and close the file: an open handle blocks the swap on Windows."""
    if not INDEX.exists():
        return {"vecs": np.zeros((0, 512), np.float32), **{f: np.array([], dtype=object) for f in FIELDS}}
    with np.load(INDEX, allow_pickle=True) as z:
        return {k: z[k].copy() for k in z.files}


def save(d):
    tmp = INDEX.with_name("search.tmp")
    with open(tmp, "wb") as f:  # a handle: np.savez would append .npz to a path
        np.savez(f, **d)
    for _ in range(5):
        try:
            os.replace(tmp, INDEX)
            return
        except PermissionError:  # Windows: a reader may hold the file briefly
            time.sleep(0.5)
    raise PermissionError("could not replace search.npz")


def update_index(con, limit=300):
    """Embed new frames that are not yet indexed (newest first, at most `limit` per call)."""
    d = load()
    have = set(d["frame_id"].tolist())
    rows = [r for r in con.execute(
        "SELECT f.frame_id, f.camera_id, c.name, c.lat, c.lon, f.fetched_at, f.image_path "
        "FROM frames f JOIN cameras c USING (camera_id) "
        "WHERE f.ok AND f.is_new AND f.image_path IS NOT NULL ORDER BY f.fetched_at DESC").fetchall()
        if r[0] not in have][:limit]
    if not rows:
        return 0
    vecs, keep = embed_images([ROOT / r[6] for r in rows])
    if not keep:
        return 0
    rows = [rows[i] for i in keep]
    new = {"vecs": np.concatenate([d["vecs"], vecs]).astype(np.float32)}
    cols = {"frame_id": [r[0] for r in rows], "camera_id": [r[1] for r in rows], "name": [r[2] for r in rows],
            "lat": [r[3] for r in rows], "lon": [r[4] for r in rows],
            "frame_time": [r[5].strftime("%Y-%m-%dT%H:%M:%SZ") for r in rows]}
    for f in FIELDS:
        new[f] = np.concatenate([d[f], np.array(cols[f], dtype=object)])
    save(new)
    return len(rows)


def rank(vecs, meta, qvec, limit):
    """Best frame per camera, highest cosine first. meta: dict of parallel arrays."""
    seen, out = set(), []
    for i in np.argsort(-(vecs @ qvec)):
        cam = meta["camera_id"][i]
        if cam in seen:
            continue
        seen.add(cam)
        out.append((int(i), float(vecs[i] @ qvec)))
        if len(out) >= limit:
            break
    return out


def selftest():
    v = np.eye(3, dtype=np.float32)
    meta = {"camera_id": np.array(["a", "a", "b"], dtype=object)}
    r = rank(v, meta, np.array([1, 0.5, 0], np.float32), 10)
    assert [i for i, _ in r] == [0, 2], r  # one result per camera, best first
    assert blocked("man in a red jacket") and blocked("license plate ABC") and not blocked("snowy road")
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--query")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.limit:
        from vision.store.db import connect
        con = connect()
        try:
            print(f"embedded {update_index(con, a.limit)} frames")
        finally:
            con.close()
    if a.query:
        if blocked(a.query):
            raise SystemExit("refused: person search is out of scope")
        d = load()
        for i, s in rank(d["vecs"], d, embed_text(a.query), 5):
            print(f"{s:.3f} {d['frame_id'][i]} {d['name'][i]}")
