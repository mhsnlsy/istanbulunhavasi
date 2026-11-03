# İstanbul'un Havası 4.0

Static GitHub Pages dashboard for Istanbul.

## Data sources

- Forecast: Open-Meteo GFS API, coordinates 41.014, 28.950, Europe/Istanbul timezone. The dashboard requests hourly 2 m temperature, humidity, dew point, precipitation, sea-level pressure, 10 m wind and 850 hPa temperature, plus daily summaries.
- ENKA Balmumcu: ENKA public Vantage PRO current-value table. Browser-side parser reads the published table; ENKA values are not used to fill MGM fields.
- MGM Eyüpsultan 18101: isolated feed contract at `data/mgm-18101.json`. This deployment intentionally starts unconfigured. Populate it only after verifying the authoritative MGM endpoint and station identity. No nearby station is silently substituted.

## Develop

Open `index.html` through a local static server. No build step or API key is required.

## Deploy

GitHub Actions publishes the repository root to GitHub Pages after each push to `main`. In repository Settings → Pages, set Source to **GitHub Actions**.

## Notes

Live data availability depends on upstream provider CORS/access policies. If ENKA blocks browser cross-origin requests, move its parser to a scheduled GitHub Actions fetch and publish a JSON snapshot. The app displays missing data explicitly rather than synthesizing observations.
