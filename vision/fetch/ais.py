"""AISStream logger for the English Channel. Run: python -m vision.fetch.ais
Writes to data/ais.duckdb (separate file from vision.duckdb: DuckDB allows one writer per file on Windows)."""
import asyncio
import json
import os
import time
from datetime import datetime, timezone

import duckdb
import websockets

from vision.store.db import ROOT

BBOX = [[[50.0, -1.5], [51.5, 2.0]]]  # Dover Strait / eastern Channel: [[lat, lon], [lat, lon]]
URL = "wss://stream.aisstream.io/v0/stream"
DB = ROOT / "data" / "ais.duckdb"
FLUSH_S = 60


def api_key():
    if os.environ.get("AISSTREAM_API_KEY"):
        return os.environ["AISSTREAM_API_KEY"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("AISSTREAM_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("AISSTREAM_API_KEY missing")


def flush(rows):
    con = duckdb.connect(str(DB))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS ais (mmsi BIGINT, t TIMESTAMP, lat DOUBLE, lon DOUBLE, "
                    "sog DOUBLE, cog DOUBLE, name TEXT)")
        con.executemany("INSERT INTO ais VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        con.close()


async def stream_once(key):
    rows, last = [], time.time()
    try:
        async with websockets.connect(URL, open_timeout=45) as ws:
            await ws.send(json.dumps({"APIKey": key, "BoundingBoxes": BBOX, "FilterMessageTypes": ["PositionReport"]}))
            async for raw in ws:
                m = json.loads(raw)
                if "error" in m:
                    raise RuntimeError(m["error"])
                p = m.get("Message", {}).get("PositionReport")
                if not p:  # e.g. SubscriptionConfirmation
                    continue
                meta = m["MetaData"]
                rows.append((meta["MMSI"], datetime.now(timezone.utc).replace(tzinfo=None), p["Latitude"],
                             p["Longitude"], p["Sog"], p["Cog"], meta.get("ShipName", "").strip()))
                if time.time() - last > FLUSH_S:
                    flush(rows)
                    print(f"[ais] flushed {len(rows)}", flush=True)
                    rows, last = [], time.time()
    finally:
        if rows:  # a drop must not lose the buffered minute
            flush(rows)


async def main():
    key = api_key()
    while True:  # reconnect forever; the stream drops now and then
        try:
            await stream_once(key)
        except Exception as e:
            print(f"[ais] {e!r}", flush=True)
        await asyncio.sleep(10)  # also after a clean close: no hot reconnect loop


if __name__ == "__main__":
    asyncio.run(main())
