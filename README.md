# İstanbul'un Havası 4.0

Responsive Istanbul weather dashboard matching the supplied dark two-column reference. The GitHub Actions collector writes static JSON snapshots; the web page reads those snapshots and does not scrape meteorological providers from the browser.

## Data sources and identity

- **MGM Eyüpsultan 18101:** The collector resolves station number 18101 through MGM's public `/web/merkezler` and `/web/istasyonlar` directory endpoints, reads the matching `merkezId`, then requests `/web/sondurumlar?merkezid=<merkezId>`. It verifies the returned `istNo` is 18101. It never treats 18101 as a `merkezId` without resolving it, and never substitutes a nearby station. Historical station metadata: 41.10 N, 28.55 E, 54 m.
- **ENKA Balmumcu:** The public ENKA Vantage Pro current-values table at https://w.enka.com/weather/currentvaluestr.html. The collector parses temperature, feels-like, pressure, humidity, dew point, wind, and daily rain, converting knots to km/h.
- **GFS:** NCEP GFS 0.25° through Open-Meteo's Single Runs API, at 41.014, 28.950. Each forecast is requested by its UTC initialization time using the `run` parameter. The four latest available 00Z/06Z/12Z/18Z runs are stored separately and compared on common valid times. Hourly variables include 2 m temperature, humidity, dew point, precipitation, sea-level pressure, 10 m wind and 850 hPa temperature; daily data drives the 8-day cards.

The MeteoPT link supplied for the project is the model/location reference. The current collector does **not** parse the MeteoPT page itself; it retrieves the same NCEP GFS model family through the documented Single Runs API so individual cycles remain addressable. This source distinction is also reflected in the interface.

## Five-minute archive

- The `Collect and publish Istanbul weather` workflow runs on pushes, manual dispatch, and every five minutes.
- Successful MGM and ENKA samples are appended to a rolling 24-hour series (maximum 300 samples per station).
- The latest four successful GFS cycles are retained as full forecast runs. An unpublished cycle does not erase previously archived cycles.
- Each workflow execution validates Python, JavaScript and JSON, commits updated archive files, then publishes the Pages artifact.
- Provider errors are stored and surfaced. The last good station record is retained and marked stale rather than replaced with invented values.
- GitHub scheduled runs are best-effort; five minutes is the target cadence, not a hard real-time service guarantee.

## GitHub Pages

Repository Settings → Pages → Build and deployment → Source: **GitHub Actions**.

The site cannot deploy until Pages is enabled for this repository. Then use Actions → **Collect and publish Istanbul weather** → **Run workflow** for an immediate initial collection and publication.

## Local validation

```bash
python -m py_compile scripts/collect_weather.py
node --check assets/app.js
python -m json.tool data/dashboard.json
```
