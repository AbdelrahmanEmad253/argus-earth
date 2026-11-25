import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from PIL import Image, ImageStat

from vision.fetch.cameras import UA
from vision.store.db import FRAMES, ROOT

NIGHT_LUMA = 40  # mean 0-255 luminance below this = night; guess, calibrate on real night frames


def _download(cam):
    try:
        r = requests.get(cam["image_url"], headers=UA, timeout=15)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("L")  # trust boundary: must decode
        return cam, r.content, ImageStat.Stat(img).mean[0] < NIGHT_LUMA
    except Exception:
        return cam, None, None


def fetch_cycle(con, cams, workers=8):
    """One pass over all cameras; every attempt (even failed) is a frames row."""
    con.executemany("INSERT INTO cameras VALUES (?,?,?,?,?,?,NULL) ON CONFLICT DO NOTHING",
                    [(c["camera_id"], c["source"], c["name"], c["lat"], c["lon"], c["image_url"]) for c in cams])
    last = dict(con.execute(
        "SELECT camera_id, image_hash FROM frames WHERE ok QUALIFY row_number() OVER "
        "(PARTITION BY camera_id ORDER BY fetched_at DESC)=1").fetchall())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(_download, cams))
    n_ok = n_new = 0
    for cam, data, night in results:
        fid = f"{cam['camera_id']}_{now:%Y%m%dT%H%M%SZ}"
        if data is None:
            con.execute("INSERT INTO frames VALUES (?,?,?,false,false,NULL,NULL,NULL) ON CONFLICT DO NOTHING",
                        [fid, cam["camera_id"], now])
            continue
        h = hashlib.sha256(data).hexdigest()
        # ponytail: hash only catches byte-identical repeats; a camera re-stamping the same scene looks "new"
        new = h != last.get(cam["camera_id"])
        path = None
        if new:
            p = FRAMES / f"{fid}.jpg"
            p.write_bytes(data)
            path = p.relative_to(ROOT).as_posix()
        con.execute("INSERT INTO frames VALUES (?,?,?,true,?,?,?,?) ON CONFLICT DO NOTHING",
                    [fid, cam["camera_id"], now, new, path, h, bool(night)])
        n_ok += 1
        n_new += new
    return len(cams), n_ok, n_new
