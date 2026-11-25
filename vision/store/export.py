"""Write web/public/vision/latest.json (contract/README.md). Atomic: tmp file then replace."""
import json
import os
import time
from datetime import datetime, timezone

from vision.store.db import ROOT, connect

OUT = ROOT / "web" / "public" / "vision" / "latest.json"
FEATURES = ("density", "weather", "people_bikes")


def z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(con):
    rows = con.execute("""
        SELECT c.camera_id, c.lat, c.lon, f.fetched_at, f.is_night, f.frame_id
        FROM cameras c JOIN frames f USING (camera_id)
        WHERE f.ok AND f.is_new
        QUALIFY row_number() OVER (PARTITION BY c.camera_id ORDER BY f.fetched_at DESC) = 1
        ORDER BY c.camera_id""").fetchall()
    res = {}
    ids = [r[5] for r in rows]  # only the frames being exported, not all history
    for fid, feat, val in con.execute("SELECT frame_id, feature, value_json FROM results "
                                      "WHERE list_contains(?, frame_id)", [ids]).fetchall():
        res[(fid, feat)] = json.loads(val)
    cams = [dict(camera_id=cid, lat=lat, lon=lon, frame_time=z(t), is_night=bool(night),
                 **{f: res.get((fid, f)) for f in FEATURES})  # missing result -> null (not computed yet)
            for cid, lat, lon, t, night, fid in rows]
    return {"schema_version": 1, "generated_at": z(datetime.now(timezone.utc)), "cameras": cams}


def export():
    con = connect()
    try:
        doc = build(con)
    finally:
        con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    for _ in range(5):  # browser never sees a half-written file
        try:
            os.replace(tmp, OUT)
            break
        except PermissionError:  # Windows: the dev server may hold the file open
            time.sleep(0.5)
    else:
        OUT.write_text(tmp.read_text())  # ponytail: non-atomic fallback; readers may rarely see a partial file
    return len(doc["cameras"])


if __name__ == "__main__":
    print(f"exported {export()} cameras")
