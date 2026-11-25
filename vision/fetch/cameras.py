import re

import requests

UA = {"User-Agent": "ArgusEarth/0.1 (open-source research)"}
ANCHORS = {"caltrans": (34.0537, -118.2428), "austin": (30.2672, -97.7431), "tfl": (51.5074, -0.1278)}


def _get(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def load_caltrans(district=7):
    out = []
    for x in _get(f"https://cwwp2.dot.ca.gov/data/d{district}/cctv/cctvStatusD{district:02d}.json")["data"]:
        c = x["cctv"]
        url = c.get("imageData", {}).get("static", {}).get("currentImageURL")
        m = re.search(r"/image/([^/]+)/", url or "")
        if c.get("inService") != "true" or not m:
            continue
        loc = c["location"]
        out.append(dict(camera_id=f"caltrans_d{district}_{m[1]}", source="caltrans", name=loc["locationName"],
                        lat=float(loc["latitude"]), lon=float(loc["longitude"]), image_url=url))
    return out


def load_austin():
    out = []
    for c in _get("https://data.austintexas.gov/resource/b4k4-adkb.json?$limit=2000"):
        if c.get("camera_status") != "TURNED_ON" or "location" not in c:
            continue
        lon, lat = c["location"]["coordinates"]
        out.append(dict(camera_id=f"austin_{c['camera_id']}", source="austin", name=c["location_name"],
                        lat=lat, lon=lon, image_url=c["screenshot_address"]))
    return out


def load_tfl():
    out = []
    for c in _get("https://api.tfl.gov.uk/Place/Type/JamCam"):
        p = {a["key"]: a["value"] for a in c["additionalProperties"]}
        if p.get("available") != "true" or not p.get("imageUrl"):
            continue
        out.append(dict(camera_id="tfl_" + c["id"].removeprefix("JamCams_"), source="tfl", name=c["commonName"],
                        lat=c["lat"], lon=c["lon"], image_url=p["imageUrl"]))
    return out


LOADERS = {"caltrans": load_caltrans, "austin": load_austin, "tfl": load_tfl}


def pick(cams, source, n):
    """n cameras nearest the city centre (squared degrees: fine at city scale)."""
    la, lo = ANCHORS[source]
    return sorted(cams, key=lambda c: (c["lat"] - la) ** 2 + (c["lon"] - lo) ** 2)[:n]


def load(sources, per_source):
    cams = []
    for s in sources:
        try:
            cams += pick(LOADERS[s](), s, per_source)
        except Exception as e:  # one dead source must not kill the others
            print(f"[cameras] {s} failed: {e}", flush=True)
    return cams
