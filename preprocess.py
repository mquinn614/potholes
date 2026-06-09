"""
Preprocess NYC pothole CSV → compact binary for browser rendering.

Output: data.bin (parallel arrays) + meta.json (small).
- Centroid (lon, lat) per repaired segment
- Month index (months since 2010-01)
- Boro index (M=0, B=1, Q=2, X=3, S=4)
- Mayor index (Bloomberg=0, de Blasio=1, Adams=2, Mamdani=3)

Sorted ascending by month so the browser can binary-search a current frame.
"""

import csv, json, re, struct, sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median

csv.field_size_limit(sys.maxsize)

# Find the source CSV — newest by mtime wins, so a fresh download is never
# shadowed by an older export that happens to sort first alphabetically.
HERE = Path(__file__).resolve().parent
candidates = (
    list(HERE.glob("Street_Pothole_Work_Orders*.csv"))
    + list(HERE.parent.glob("Street_Pothole_Work_Orders*.csv"))
)
if not candidates:
    sys.exit("No NYC pothole CSV found next to this script or in its parent directory.")
SRC = max(candidates, key=lambda p: p.stat().st_mtime)
OUT_DIR = HERE
print(f"Source CSV: {SRC}")

BORO = {"M": 0, "B": 1, "Q": 2, "X": 3, "S": 4}
BORO_NAMES = ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]

# Mayor terms — sworn in Jan 1
MAYORS = [
    ("Michael Bloomberg",   2010,  1, 2013, 12),  # truncated to dataset start
    ("Bill de Blasio",      2014,  1, 2021, 12),
    ("Eric Adams",          2022,  1, 2025, 12),
    ("Zohran Mamdani",      2026,  1, 2099, 12),
]

EPOCH_Y, EPOCH_M = 2010, 1

def month_idx(y, m):
    return (y - EPOCH_Y) * 12 + (m - EPOCH_M)

def mayor_idx(y, m):
    for i, (_, sy, sm, ey, em) in enumerate(MAYORS):
        if (y, m) >= (sy, sm) and (y, m) <= (ey, em):
            return i
    return 0

# Pull every (lon, lat) pair out of WKT; average for centroid.
PT_RE = re.compile(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)")

def centroid(wkt):
    pts = PT_RE.findall(wkt)
    if not pts:
        return None
    sx = sy = 0.0
    for x, y in pts:
        sx += float(x); sy += float(y)
    n = len(pts)
    return (sx / n, sy / n)

print(f"Reading {SRC.name}…")
events = []
skipped = 0
# Days from report to close, citizen-sourced (CTZ) orders only, keyed by
# close month. Crew-initiated orders (YRD etc.) are logged as the work
# happens, so their lag is ~0 and says nothing about responsiveness.
ctz_lags = defaultdict(list)
with SRC.open(newline="") as f:
    r = csv.DictReader(f)
    for row in r:
        d = row["RptClosed"]
        if not d or len(d) != 10:
            skipped += 1; continue
        try:
            mm, dd, yyyy = d.split("/")
            y, m = int(yyyy), int(mm)
        except ValueError:
            skipped += 1; continue
        if y < EPOCH_Y or y > 2030:
            skipped += 1; continue

        b = BORO.get(row["Boro"])
        if b is None:
            skipped += 1; continue

        c = centroid(row["the_geom"])
        if c is None:
            skipped += 1; continue

        # Sanity: NYC bbox roughly lon -74.3..-73.7, lat 40.4..40.95
        lon, lat = c
        if not (-74.4 < lon < -73.6 and 40.3 < lat < 41.0):
            skipped += 1; continue

        mo = month_idx(y, m)
        events.append((mo, b, mayor_idx(y, m), lon, lat))

        if (row.get("Source") or "").strip() == "CTZ":
            try:
                rmm, rdd, ryyyy = (row.get("RptDate") or "").split("/")
                lag = (date(y, m, int(dd)) - date(int(ryyyy), int(rmm), int(rdd))).days
                if lag >= 0:
                    ctz_lags[mo].append(lag)
            except ValueError:
                pass

print(f"Parsed {len(events)} events, skipped {skipped}.")

events.sort(key=lambda e: e[0])
N = len(events)

# Pack parallel arrays into one binary file:
#   u32  N
#   u8[N] boro
#   u8[N] mayor
#   pad to 4
#   u16[N] month
#   pad to 4
#   f32[N*2] coords (lon, lat per event)
def pad(buf, align):
    while len(buf) % align:
        buf.append(0)

buf = bytearray()
buf += struct.pack("<I", N)
for _, b, _, _, _ in events: buf.append(b)
for _, _, ma, _, _ in events: buf.append(ma)
pad(buf, 4)
for mo, *_ in events: buf += struct.pack("<H", mo)
pad(buf, 4)
for _, _, _, lon, lat in events:
    buf += struct.pack("<ff", lon, lat)

(OUT_DIR / "data.bin").write_bytes(bytes(buf))

# Per-month tallies for the running counter / histogram.
last_month = events[-1][0]
months_total = last_month + 1
monthly = [[0, 0, 0, 0, 0] for _ in range(months_total)]  # 5 boros
for mo, b, _, _, _ in events:
    monthly[mo][b] += 1

month_labels = []
y, m = EPOCH_Y, EPOCH_M
for _ in range(months_total):
    month_labels.append(f"{y}-{m:02d}")
    m += 1
    if m > 12:
        m = 1; y += 1

# Monthly median wait for citizen-reported potholes (None where no CTZ
# closures that month).
ctz_lag_median = [
    round(median(ctz_lags[i]), 1) if ctz_lags.get(i) else None
    for i in range(months_total)
]
known = [v for v in ctz_lag_median if v is not None]
print(f"CTZ lag medians: min {min(known)}d, max {max(known)}d across {len(known)} months")

meta = {
    "n": N,
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "dataThrough": month_labels[last_month],
    "epoch": {"year": EPOCH_Y, "month": EPOCH_M},
    "months": months_total,
    "monthLabels": month_labels,
    "monthlyByBoro": monthly,
    "ctzLagMedian": ctz_lag_median,
    "boros": BORO_NAMES,
    "mayors": [
        {"name": MAYORS[0][0], "start": "2002-01", "actualStart": "2010-01", "end": "2013-12"},
        {"name": MAYORS[1][0], "start": "2014-01", "end": "2021-12"},
        {"name": MAYORS[2][0], "start": "2022-01", "end": "2025-12"},
        {"name": MAYORS[3][0], "start": "2026-01", "end": None},
    ],
    "annotations": [
        {"month": "2012-10", "label": "Hurricane Sandy"},
        {"month": "2014-01", "label": "Polar vortex"},
        {"month": "2015-02", "label": "Brutal winter"},
        {"month": "2018-01", "label": "Bomb cyclone"},
        {"month": "2020-03", "label": "COVID-19 lockdown"},
        {"month": "2022-01", "label": "Adams takes office"},
        {"month": "2014-01", "label": "de Blasio takes office"},
        {"month": "2026-01", "label": "Mamdani takes office"},
    ],
}
(OUT_DIR / "meta.json").write_text(json.dumps(meta))

size_mb = (OUT_DIR / "data.bin").stat().st_size / (1024*1024)
print(f"Wrote data.bin ({size_mb:.2f} MB) and meta.json")
