-- DRAFT v1: agree with Rowaina before changing. Single source of truth for data/vision.duckdb.
CREATE TABLE IF NOT EXISTS cameras (
  camera_id TEXT PRIMARY KEY,  -- '<source>_<id>', e.g. 'caltrans_d7_i110196avenue26offramp'
  source    TEXT,              -- 'caltrans' | 'austin' | 'tfl'
  name      TEXT,
  lat       DOUBLE,
  lon       DOUBLE,
  image_url TEXT,
  active    BOOLEAN            -- false if no new image for 24 h
);
CREATE TABLE IF NOT EXISTS frames (
  frame_id   TEXT PRIMARY KEY, -- '<camera_id>_<YYYYMMDDTHHMMSSZ>'
  camera_id  TEXT REFERENCES cameras(camera_id),
  fetched_at TIMESTAMP,        -- naive UTC
  ok         BOOLEAN,
  is_new     BOOLEAN,
  image_path TEXT,             -- NULL after deletion
  image_hash TEXT,
  is_night   BOOLEAN
);
CREATE TABLE IF NOT EXISTS results (
  frame_id   TEXT REFERENCES frames(frame_id),
  feature    TEXT,             -- 'density' | 'weather' | 'people_bikes' | 'smoke'
  model      TEXT,
  value_json TEXT,
  created_at TIMESTAMP,
  PRIMARY KEY (frame_id, feature)
);
