"""YOLO11n vehicle counts -> results(feature='density'). Run: python -m vision.models.yolo [--limit N]"""
import argparse
import json
from datetime import datetime, timezone

from vision.store.db import ROOT, connect

MODEL = "yolo11n-coco"
CONF = 0.25  # guess; tune against hand-checked frames
CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}  # COCO ids
_model = None


def count(path):
    global _model
    if _model is None:
        from ultralytics import YOLO
        (ROOT / "data" / "models").mkdir(parents=True, exist_ok=True)
        _model = YOLO(str(ROOT / "data" / "models" / "yolo11n.pt"))  # downloads here on first use
    r = _model.predict(str(path), classes=list(CLASSES), conf=CONF, verbose=False)[0]
    out = dict.fromkeys(CLASSES.values(), 0)
    for c in r.boxes.cls.tolist():
        out[CLASSES[int(c)]] += 1
    out["total"] = sum(out.values())
    return out


def run_density(con, limit=None):
    """Count vehicles on every new frame that has an image and no density result yet."""
    rows = con.execute(
        "SELECT frame_id, image_path FROM frames f WHERE ok AND is_new AND image_path IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM results r WHERE r.frame_id=f.frame_id AND r.feature='density') "
        "ORDER BY fetched_at DESC" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for fid, p in rows:
        con.execute("INSERT INTO results VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
                    [fid, "density", MODEL, json.dumps(count(ROOT / p)), now])
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    con = connect()
    try:
        print(f"density rows: {run_density(con, ap.parse_args().limit)}")
    finally:
        con.close()
