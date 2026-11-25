from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "vision.duckdb"
FRAMES = ROOT / "data" / "frames"


def connect():
    """Open per cycle and close after: a long-held handle locks the file on Windows."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute((ROOT / "contract" / "schema.sql").read_text())
    return con
