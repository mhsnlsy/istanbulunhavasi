#!/usr/bin/env python3
"""Five-minute collector for MGM Eyupsultan, ENKA Balmumcu and NCEP GFS runs."""
from __future__ import annotations
import html, json, math, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DASHBOARD = DATA / "dashboard.json"
ISTANBUL = ZoneInfo("Europe/Istanbul")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
MGM_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.mgm.gov.tr", "Referer": "https://www.mgm.gov.tr/"}
HOURLY = "temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,pressure_msl,wind_speed_10m,wind_direction_10m,temperature_850hPa"
DAILY = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"

def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)

def stamp(value=None):
    return (value or now_utc()).isoformat().replace("+00:00", "Z")

def load_json(path, fallback):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return fallback

def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

def fetch(url, headers=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200: raise RuntimeError("HTTP %s: %s" % (response.status, url))
        return response.read()

def fetch_json(url, headers=None, timeout=25):
    try: return json.loads(fetch(url, headers, timeout).decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc: raise RuntimeError("Invalid JSON response: %s" % exc) from exc

def num(value):
    if value is None or isinstance(value, bool): return None
    try: result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError): return None
    if not math.isfinite(result) or abs(result) >= 9990:
        return None
    return result

def dewpoint(temp, rh):
    if temp is None or rh is None or rh <= 0 or rh > 100: return None
    a, b = 17.625, 243.04
    gamma = math.log(rh / 100) + a * temp / (b + temp)
    return round(b * gamma / (a - gamma), 1)

def trim_history(items, now):
    cutoff = now - timedelta(hours=24)
    out = []
    for item in items if isinstance(items, list) else []:
        try:
            t = datetime.fromisoformat(item["recorded_at"].replace("Z", "+00:00"))
            if t >= cutoff: out.append(item)
        except (KeyError, TypeError, ValueError): pass
    return out[-300:]

def add_sample(station, now):
    cur = station.get("current", {})
    history = station.get("history", [])
    history.append({
        "recorded_at": stamp(now), "source_time": station.get("source_time"),
        "temperature": cur.get("temperature"), "humidity": cur.get("humidity"),
        "wind_speed": cur.get("wind_speed"), "wind_direction": cur.get("wind_direction"),
        "pressure": cur.get("pressure"), "rain": cur.get("rain")
    })
    station["history"] = trim_history(history, now)

def collect_mgm(now):
    # 18101 is the MGM station number (sondurumIstNo), not necessarily
    # the centerId parameter accepted by /sondurumlar.
    candidates = []
    endpoints = [
        "https://servis.mgm.gov.tr/web/merkezler?il=istanbul&ilce=eyup",
        "https://servis.mgm.gov.tr/web/merkezler?il=istanbul&ilce=eyupsultan",
        "https://servis.mgm.gov.tr/web/merkezler/ililcesi?il=istanbul",
        "https://servis.mgm.gov.tr/web/istasyonlar"
    ]
    seen = set()
    selected = None
    for endpoint in endpoints:
        try:
            payload = fetch_json(endpoint, MGM_HEADERS, timeout=12)
            rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
            for item in rows:
                if not isinstance(item, dict):
                    continue
                marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if marker not in seen:
                    candidates.append(item)
                    seen.add(marker)
        except Exception as exc:
            print("MGM station directory unavailable:", endpoint, exc, file=sys.stderr)

        for item in candidates:
            station_no = next((item.get(key) for key in
                ("sondurumIstNo", "istNo", "istno", "istasyonNo", "istasyon_no")
                if item.get(key) is not None), None)
            center_id = item.get("merkezId") or item.get("merkezid")
            if str(station_no) == "18101" and center_id is not None:
                selected = item
                break
        if selected is not None:
            break
    if selected is None:
        raise RuntimeError(
            "MGM directory did not resolve station 18101 to a current centerId; "
            "no nearby station was substituted."
        )

    center_id = selected.get("merkezId") or selected.get("merkezid")
    data = fetch_json(
        "https://servis.mgm.gov.tr/web/sondurumlar?merkezid=" + urllib.parse.quote(str(center_id)),
        MGM_HEADERS
    )
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("MGM center %s has no current observation for station 18101" % center_id)
    row = data[0]
    returned_station = next((row.get(key) for key in
        ("istNo", "istno", "sondurumIstNo", "istasyonNo")
        if row.get(key) is not None), None)
    if returned_station is not None and str(returned_station) != "18101":
        raise RuntimeError(
            "MGM identity mismatch: centerId %s returned station %s, not 18101"
            % (center_id, returned_station)
        )

    temp, humidity = num(row.get("sicaklik")), num(row.get("nem"))
    station_pressure = num(row.get("aktuelBasinc"))
    sea_pressure = num(row.get("denizeIndirgenmisBasinc"))
    current = {
        "temperature": temp,
        "feels_like": num(row.get("hissedilenSicaklik") or row.get("hissedilen")),
        "humidity": humidity,
        "wind_speed": num(row.get("ruzgarHiz")),
        "wind_direction": num(row.get("ruzgarYon")),
        "dew_point": dewpoint(temp, humidity),
        "rain": num(row.get("yagis00Now")),
        "pressure": sea_pressure if sea_pressure is not None else station_pressure,
        "station_pressure": station_pressure,
        "sea_level_pressure": sea_pressure,
        "weather_code": row.get("hadiseKodu")
    }
    if not any(current.get(k) is not None for k in ("temperature", "humidity", "wind_speed", "pressure")):
        raise RuntimeError("MGM response has no usable measurements")
    observed = row.get("veriZamani") or row.get("olcumZamani")
    return {
        "station_id": "18101", "station_center_id": center_id,
        "station_name": "Eyüpsultan", "latitude": 41.10,
        "longitude": 28.55, "elevation_m": 54,
        "source": "MGM · 18101 · servis.mgm.gov.tr",
        "status": "ok", "updated_at": observed, "recorded_at": stamp(now), "fetched_at": stamp(now),
        "source_time": observed, "current": current, "error": None
    }

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts = []
    def handle_data(self, data):
        clean = " ".join(data.split())
        if clean: self.parts.append(clean)

def after_label(text, label, unit=""):
    # ENKA's table sometimes places the value immediately after a label
    # without a real whitespace character, depending on its HTML markup.
    position = text.casefold().find(label.casefold())
    if position < 0:
        return None
    tail = text[position + len(label):position + len(label) + 100]
    match = re.search(r"(-?\d+(?:[.,]\d+)?)", tail)
    return num(match.group(1)) if match else None

COMPASS = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,"SE":135,"SSE":157.5,"S":180,"SSW":202.5,"SW":225,"WSW":247.5,"W":270,"WNW":292.5,"NW":315,"NNW":337.5}

def collect_enka(now):
    raw = fetch("https://w.enka.com/weather/currentvaluestr.html", {"Accept":"text/html,application/xhtml+xml"})
    parser = TextParser(); parser.feed(raw.decode("utf-8", errors="replace"))
    text = html.unescape(" ".join(parser.parts))
    temp = after_label(text, "Günlük Sıcaklık", "°C")
    feel = after_label(text, "Hissedilen Sıcaklık", "°C")
    pressure = after_label(text, "Barometre (hPa)")
    humidity = after_label(text, "Bağıl Nem", "%")
    dew = after_label(text, "Yoğuşma Noktası", "°C")
    rain = after_label(text, "Günlük Yağış", "mm")
    wind_pos = text.casefold().find("rüzgar")
    wind_tail = text[wind_pos + len("rüzgar"):wind_pos + len("rüzgar") + 100] if wind_pos >= 0 else ""
    wind = re.search(r"([A-Z]{1,3})\s+(-?\d+(?:[.,]\d+)?)\s*kt", wind_tail, re.I)
    speed = num(wind.group(2)) * 1.852 if wind and num(wind.group(2)) is not None else None
    direction = COMPASS.get(wind.group(1).upper()) if wind else None
    if temp is None and pressure is None and humidity is None:
        raise RuntimeError("ENKA page is missing expected Vantage Pro fields")
    source_time = None
    tm = re.search(r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})", text)
    if tm:
        try: source_time = datetime.strptime(tm.group(1)+" "+tm.group(2), "%d/%m/%y %H:%M").replace(tzinfo=ISTANBUL).isoformat()
        except ValueError: pass
    return {
        "station_id":"ENKA-BALMUMCU", "station_name":"Balmumcu",
        "latitude":41.1, "longitude":28.9, "elevation_m":107,
        "source":"ENKA · Vantage Pro", "status":"ok", "updated_at":source_time,
        "recorded_at":stamp(now), "fetched_at":stamp(now), "source_time":source_time,
        "current":{"temperature":temp,"feels_like":feel,"humidity":humidity,
                   "wind_speed":round(speed,1) if speed is not None else None,
                   "wind_direction":direction,"dew_point":dew,"rain":rain,
                   "pressure":pressure,"weather_code":None},
        "error":None
    }

def cycle_candidates(now):
    # GFS runs at 00Z/06Z/12Z/18Z; allow three hours for routine publication.
    cursor = now - timedelta(hours=3)
    cursor = cursor.replace(hour=(cursor.hour // 6)*6, minute=0, second=0, microsecond=0)
    return [cursor - timedelta(hours=6*i) for i in range(12)]

def fetch_gfs(run_time):
    params = {
        "latitude":"41.014", "longitude":"28.950", "hourly":HOURLY, "daily":DAILY,
        "models":"ncep_gfs025", "run":run_time.strftime("%Y-%m-%dT%H:00"),
        "forecast_days":"8", "timezone":"Europe/Istanbul",
        "wind_speed_unit":"kmh", "precipitation_unit":"mm", "temperature_unit":"celsius"
    }
    url = "https://single-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    payload = fetch_json(url, {"Accept":"application/json"}, timeout=18)
    hourly = payload.get("hourly") if isinstance(payload, dict) else None
    if not isinstance(hourly, dict) or not hourly.get("time"):
        raise RuntimeError("GFS run %s has no hourly forecast" % run_time.isoformat())
    if abs(float(payload.get("latitude", 41.014)) - 41.014) > 0.2 or abs(float(payload.get("longitude", 28.950)) - 28.950) > 0.2:
        raise RuntimeError("GFS service returned unexpected coordinates")
    return {
        "run":run_time.strftime("%Y-%m-%dT%H:%MZ"), "run_cycle":run_time.strftime("%H")+"Z",
        "fetched_at":stamp(), "model":"NCEP GFS 0.25°", "model_id":"ncep_gfs025",
        "source":"Open-Meteo Single Runs API · NCEP GFS 0.25°",
        "latitude":payload.get("latitude"), "longitude":payload.get("longitude"),
        "elevation":payload.get("elevation"), "timezone":payload.get("timezone","Europe/Istanbul"),
        "hourly":hourly, "daily":payload.get("daily",{}),
        "hourly_units":payload.get("hourly_units",{}), "daily_units":payload.get("daily_units",{})
    }

def collect_gfs(existing, now):
    by_run = {item.get("run"):item for item in existing if isinstance(item,dict) and item.get("run")}
    errors = []
    for candidate in cycle_candidates(now):
        key = candidate.strftime("%Y-%m-%dT%H:%MZ")
        if key not in by_run:
            try:
                by_run[key] = fetch_gfs(candidate)
                print("GFS archive added:", key)
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, KeyError) as exc:
                message = str(exc)
                errors.append({"run":key, "error":message[:500]})
                print("GFS not available yet:", key, message, file=sys.stderr)
        if len(by_run) >= 4: break
    runs = sorted(by_run.values(), key=lambda item:item.get("run",""), reverse=True)[:4]
    return runs, errors[:6]

def refresh_station(previous, collector, now, label):
    try:
        station = collector(now)
        station["history"] = previous.get("history",[]) if isinstance(previous,dict) else []
        add_sample(station, now)
        station["history"] = trim_history(station["history"], now)
        print(label + ": OK")
        return station
    except Exception as exc:
        print(label + ": ERROR: " + str(exc), file=sys.stderr)
        stale = dict(previous) if isinstance(previous,dict) else {}
        stale.setdefault("station_name", label)
        stale["status"] = "stale" if stale.get("current") else "unavailable"
        stale["error"] = str(exc)
        stale.setdefault("history", [])
        return stale

def main():
    now = now_utc()
    dashboard = load_json(DASHBOARD, {"stations":{}, "gfs":{"runs":[]}})
    if not isinstance(dashboard,dict): dashboard = {"stations":{}, "gfs":{"runs":[]}}
    stations = dashboard.setdefault("stations",{})
    stations["mgm"] = refresh_station(stations.get("mgm",{}), collect_mgm, now, "MGM Eyüpsultan 18101")
    stations["enka"] = refresh_station(stations.get("enka",{}), collect_enka, now, "ENKA Balmumcu")
    old_runs = dashboard.get("gfs",{}).get("runs",[]) if isinstance(dashboard.get("gfs"),dict) else []
    runs, gfs_errors = collect_gfs(old_runs if isinstance(old_runs,list) else [], now)
    dashboard["gfs"] = {
        "status":"ok" if runs else "unavailable", "updated_at":stamp(now) if runs else None,
        "source":"NCEP GFS 0.25° · Open-Meteo Single Runs API",
        "requested_coordinates":{"latitude":41.014,"longitude":28.950},
        "last_error":gfs_errors[0]["error"] if gfs_errors and not runs else None,
        "recent_errors":gfs_errors, "runs":runs
    }
    dashboard["schema_version"] = 1
    dashboard["updated_at"] = stamp(now)
    dashboard["last_poll_at"] = stamp(now)
    save_json(DASHBOARD, dashboard)
    mgm = stations["mgm"]
    save_json(DATA/"mgm-18101.json", {
        "station_id":"18101", "station_name":"Eyüpsultan", "source":mgm.get("source","MGM"),
        "status":mgm.get("status","unavailable"), "updated_at":mgm.get("updated_at"),
        **(mgm.get("current") or {}), "history":mgm.get("history",[]), "error":mgm.get("error")
    })
    save_json(DATA/"enka-balmumcu.json", stations["enka"])
    print("Collector finished:", stamp(now), "GFS runs:", len(runs))
    # Provider outages are represented in JSON, not treated as a broken deployment.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
