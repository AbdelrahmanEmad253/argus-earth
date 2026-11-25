import argparse
import time
import traceback

from vision.fetch.cameras import load
from vision.fetch.fetcher import fetch_cycle
from vision.models.yolo import run_density
from vision.search.index import update_index
from vision.store.db import ROOT, connect
from vision.store.export import export

KEEP_DAYS = 7  # PLAN: raw frames are deleted after 7 days; counts stay


def expire_frames(con):
    old = con.execute("SELECT frame_id, image_path FROM frames WHERE image_path IS NOT NULL "
                      "AND fetched_at < now()::TIMESTAMP - INTERVAL (?) DAY", [KEEP_DAYS]).fetchall()
    for fid, p in old:
        (ROOT / p).unlink(missing_ok=True)
        con.execute("UPDATE frames SET image_path = NULL WHERE frame_id = ?", [fid])
    return len(old)


def cycle(cams):
    con = connect()
    try:
        total, ok, new = fetch_cycle(con, cams)
        print(f"[fetch] {total} cams, {ok} ok, {new} new", flush=True)
        print(f"[density] {run_density(con)} frames", flush=True)
        try:  # search indexing must never stop density or export
            print(f"[embed] {update_index(con)} frames", flush=True)
        except Exception:
            traceback.print_exc()
        print(f"[expire] {expire_frames(con)} frames", flush=True)
    finally:
        con.close()
    print(f"[export] {export()} cameras", flush=True)  # one process owns the DB: no cross-process lock fights


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="caltrans,austin,tfl")
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    sources, cams, n = a.sources.split(","), [], 0
    while True:
        start = time.time()
        try:
            if not cams or n % 12 == 0:  # retry if empty, refresh the lists hourly
                cams = load(sources, a.per_source) or cams  # keep the old list if a reload fails entirely
                print(f"[run] {len(cams)} cameras", flush=True)
            cycle(cams)
        except Exception:  # overnight loop must survive anything
            traceback.print_exc()
        n += 1
        if a.once:
            break
        time.sleep(max(0, 300 - (time.time() - start)))
