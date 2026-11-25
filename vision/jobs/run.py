import argparse
import time
import traceback

from vision.fetch.cameras import load
from vision.fetch.fetcher import fetch_cycle
from vision.models.yolo import run_density
from vision.store.db import connect
from vision.store.export import export


def cycle(cams):
    con = connect()
    try:
        total, ok, new = fetch_cycle(con, cams)
        print(f"[fetch] {total} cams, {ok} ok, {new} new", flush=True)
        print(f"[density] {run_density(con)} frames", flush=True)
    finally:
        con.close()
    print(f"[export] {export()} cameras", flush=True)  # one process owns the DB: no cross-process lock fights


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="caltrans,austin,tfl")
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    cams = load(a.sources.split(","), a.per_source)
    print(f"[run] {len(cams)} cameras", flush=True)
    while True:
        start = time.time()
        try:
            cycle(cams)
        except Exception:  # overnight loop must survive anything
            traceback.print_exc()
        if a.once:
            break
        time.sleep(max(0, 300 - (time.time() - start)))
