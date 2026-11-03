# İstanbul'un Havası 4.0

Responsive Istanbul weather dashboard. GitHub Actions collector writes static JSON snapshots; the page reads those snapshots (no client-side scraping).

## Data sources

- **MGM Eyüpsultan 18101**: Resolved via servis.mgm.gov.tr `/web/merkezler` + `/web/sondurumlar`. Station number 18101 is verified.
- **ENKA Balmumcu**: Parsed from https://w.enka.com/weather/currentvaluestr.html (Vantage Pro current values).
- **GFS**: **Only** from MeteoPT (`https://api.meteopt.com/gfs/json?lat=41.014&lon=28.950`). Cycles 00/06/12/18 are requested. No other GFS sources are used.

## Collection

The `Collect and publish Istanbul weather` workflow runs on push, manual dispatch, and every five minutes. It archives the last 24 h of station observations and the latest four GFS runs.

## GitHub Pages

Source: GitHub Actions. After enabling Pages, the workflow publishes the site.

## Local check

```bash
python -m py_compile scripts/collect_weather.py
node --check assets/app.js
python -m json.tool data/dashboard.json
```
