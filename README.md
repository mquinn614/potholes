# The Pothole Map

An animated, NYT-style visualization of every closed pothole work order completed by the
NYC Department of Transportation since January 2010 — about 400,000 repairs across four
mayoral terms (Bloomberg, de Blasio, Adams, Mamdani).

Live: https://mquinn614.github.io/potholes/

## How it works

- A glowing orange pulse marks each repair finished in the current month.
- Faded dots accumulate behind, tinted by who was mayor when each pothole was fixed.
- The sidebar tallies repairs for the month, the term, and all-time.
- The footer scrubber lets you autoplay through 16 years or drag the playhead manually.
- Annotations appear for major events (Sandy, polar vortex, COVID, mayoral inaugurations).

Tech: deck.gl + MapLibre, no build step. Just static files.

## Files

- `index.html` — the page (open via any HTTP server)
- `data.bin` — preprocessed binary, ~4.6 MB
- `meta.json` — month labels, monthly tallies, mayor terms, annotations
- `preprocess.py` — regenerates `data.bin` + `meta.json` from the source CSV

## Running locally

```sh
python3 -m http.server 8765
open http://localhost:8765
```

## Regenerating the data

Drop the source CSV into the repo root, then:

```sh
python3 preprocess.py
```

The CSV ([NYC OpenData: Street Pothole Work Orders — Closed](https://data.cityofnewyork.us/Transportation/Street-Pothole-Work-Orders-Closed/qye2-ndcq))
is gitignored — only the small generated artifacts are checked in.

## Data source

NYC Department of Transportation, via NYC OpenData. The dataset includes every closed
street-pothole work order: the segment geometry, the date it was reported, and the date
the report was closed. This visualization uses the close date.
