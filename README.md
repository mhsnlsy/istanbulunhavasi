# İstanbul'un Havası 4.0

Responsive Istanbul weather dashboard. GitHub Actions fetches upstream data and publishes static JSON snapshots to GitHub Pages; the browser does not scrape meteorological providers.

## Sources

- MGM Eyüpsultan 18101: the public MGM service endpoint is https://servis.mgm.gov.tr/web/sondurumlar?merkezid=18101. A 2024 Istanbul station study lists station 18101 as Eyüpsultan at 41.10 N, 28.55 E and 54 m. MGM's current Istanbul inventory page does not show this older station ID, so the collector pins the requested identifier and checks a returned ID when present. A nearby station is never substituted.
- ENKA Balmumcu: https://w.enka.com/weather/currentvaluestr.html, the public Vantage Pro current-values page. Temperature, apparent temperature, pressure, humidity, dew point, wind and daily precipitation are parsed server-side. Knots are converted to km/h.
- GFS: NCEP GFS 0.25 degree, archived as individual model cycles through the Open-Meteo Single Runs API with model ID ncep_gfs025. Coordinates are 41.014, 28.950; timestamps are Europe/Istanbul. The MeteoPT page supplied by the project owner is the location and model reference; this implementation does not scrape the MeteoPT interface. It retrieves individual NCEP GFS forecast cycles so four outputs can be compared on the same valid-time axis. Hourly fields include 2 m temperature, humidity, dew point, precipitation, sea-level pressure, 10 m wind, and 850 hPa temperature.

## Collection and archive

- GitHub Actions collect-weather workflow runs every five minutes and can also be started manually.
- MGM and ENKA samples are appended to each station's rolling 24-hour history (up to 300 samples).
- The four newest available GFS cycles (00Z, 06Z, 12Z, 18Z) are retained as separate full forecast records. A not-yet-published cycle cannot erase older runs.
- Successful samples are committed to main; the Pages deployment workflow publishes each update.
- Provider failures preserve the last good observation and mark it stale instead of fabricating values. GitHub scheduled workflows are best-effort: five minutes is the target cadence, not a hard real-time guarantee.

## Pages setup

Repository Settings → Pages → Build and deployment → Source: GitHub Actions.

## Local checks

Run python -m py_compile scripts/collect_weather.py, node --check assets/app.js, and validate data/dashboard.json with python -m json.tool.
