#!/usr/bin/env python3
"""Clean five-minute collector for İstanbul'un Havası.

Sources (strictly as specified):
- MGM Eyüpsultan station 18101 (servis.mgm.gov.tr)
- ENKA Balmumcu (https://w.enka.com/weather/currentvaluestr.html)
- GFS forecast ONLY from MeteoPT API (https://api.meteopt.com/gfs/json?lat=41.014&lon=28.950)
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DASHBOARD = DATA / "dashboard.json"
ISTANBUL = ZoneInfo("Europe/Istanbul")
UA = "Mozilla/5.0 (compatible; IstanbulunHavasi/4.0; +https://github.com/mhsnlsy/istanbulunhavasi)"
MGM_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.mgm.gov.tr",
    "Referer": "https://www.mgm.gov.tr/",
}
METEOPT_BASE = "https://api.meteopt.com/gfs/json"
LAT, LON = "41.014", "28.950"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat().replace("+00:00", "Z")


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def fetch(url: str, headers: dict | None = None, timeout: int = 25) -> bytes:
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {url}")
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(1600).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from exc


def fetch_json(url: str, headers: dict | None = None, timeout: int = 25):
    try:
        return json.loads(fetch(url, headers, timeout).decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"Invalid JSON response: {exc}") from exc


def num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or abs(result) >= 9990:
        return None
    return result


def dewpoint(temp, rh):
    if temp is None or rh is None or rh <= 0 or rh > 100:
        return None
    a, b = 17.625, 243.04
    gamma = math.log(rh / 100) + a * temp / (b + temp)
    return round(b * gamma / (a - gamma), 1)


def trim_history(items, now: datetime):
    cutoff = now - timedelta(hours=24)
    out = []
    for item in items if isinstance(items, list) else []:
        try:
            t = datetime.fromisoformat(item["recorded_at"].replace("Z", "+00:00"))
            if t >= cutoff:
                out.append(item)
        except (KeyError, TypeError, ValueError):
            pass
    return out[-300:]


def add_sample(station: dict, now: datetime) -> None:
    cur = station.get("current", {})
    history = station.get("history", [])
    history.append({
        "recorded_at": stamp(now),
        "source_time": station.get("source_time"),
        "temperature": cur.get("temperature"),
        "humidity": cur.get("humidity"),
        "wind_speed": cur.get("wind_speed"),
        "wind_direction": cur.get("wind_direction"),
        "pressure": cur.get("pressure"),
        "rain": cur.get("rain"),
    })
    station["history"] = trim_history(history, now)


def collect_mgm(now: datetime) -> dict:
    candidates = []
    endpoints = [
        "https://servis.mgm.gov.tr/web/merkezler?il=istanbul&ilce=eyup",
        "https://servis.mgm.gov.tr/web/merkezler?il=istanbul&ilce=eyupsultan",
        "https://servis.mgm.gov.tr/web/merkezler/ililcesi?il=istanbul",
        "https://servis.mgm.gov.tr/web/istasyonlar",
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
        raise RuntimeError("MGM directory did not resolve station 18101 to a current centerId")

    center_id = selected.get("merkezId") or selected.get("merkezid")
    data = fetch_json(
        "https://servis.mgm.gov.tr/web/sondurumlar?merkezid=" + urllib.parse.quote(str(center_id)),
        MGM_HEADERS,
    )
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError(f"MGM center {center_id} has no current observation for station 18101")
    row = data[0]
    returned_station = next((row.get(key) for key in
        ("istNo", "istno", "sondurumIstNo", "istasyonNo")
        if row.get(key) is not None), None)
    if returned_station is not None and str(returned_station) != "18101":
        raise RuntimeError(f"MGM identity mismatch: centerId {center_id} returned station {returned_station}")

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
        "weather_code": row.get("hadiseKodu"),
    }
    if not any(current.get(k) is not None for k in ("temperature", "humidity", "wind_speed", "pressure")):
        raise RuntimeError("MGM response has no usable measurements")
    observed = row.get("veriZamani") or row.get("olcumZamani")
    return {
        "station_id": "18101",
        "station_center_id": center_id,
        "station_name": "Eyüpsultan",
        "latitude": 41.10,
        "longitude": 28.55,
        "elevation_m": 54,
        "source": "MGM · 18101 · servis.mgm.gov.tr",
        "status": "ok",
        "updated_at": observed,
        "recorded_at": stamp(now),
        "fetched_at": stamp(now),
        "source_time": observed,
        "current": current,
        "error": None,
    }


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        clean = " ".join(data.split())
        if clean:
            self.parts.append(clean)


def after_label(text: str, label: str, unit: str = "") -> float | None:
    number = r"(-?\d{1,4}(?:[.,]\d+)?)"
    suffix = {"°C": r"\s*°\s*C", "%": r"\s*%", "mm": r"\s*mm\b", "hPa": r""}.get(unit, r"")
    pattern = re.compile(re.escape(label) + r"\s*[:：]?\s*" + number + suffix, re.IGNORECASE)
    for match in pattern.finditer(text):
        value = num(match.group(1))
        if value is None:
            continue
        if unit == "°C" and not -80 <= value <= 65:
            continue
        if unit == "%" and not 0 <= value <= 100:
            continue
        if unit == "mm" and not 0 <= value <= 2000:
            continue
        if unit == "hPa" and not 850 <= value <= 1100:
            continue
        return value
    return None


COMPASS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5,
    "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def collect_enka(now: datetime) -> dict:
    raw = fetch("https://w.enka.com/weather/currentvaluestr.html", {"Accept": "text/html,application/xhtml+xml"})
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = raw.decode("cp1254", errors="replace")
    if "�" in decoded and b"\x96" in raw:
        decoded = raw.decode("cp1254", errors="replace")
    parser = TextParser()
    parser.feed(decoded)
    text = html.unescape(" ".join(parser.parts))
    temp = after_label(text, "Günlük Sıcaklık", "°C")
    feel = after_label(text, "Hissedilen Sıcaklık", "°C")
    pressure = after_label(text, "Barometre (hPa)", "hPa")
    humidity = after_label(text, "Bağıl Nem", "%")
    dew = after_label(text, "Yoğuşma Noktası", "°C")
    rain = after_label(text, "Günlük Yağış", "mm")
    wind = re.search(
        r"\bRüzgar\s+(NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW|N)\s+(-?\d+(?:[.,]\d+)?)\s*kt\b",
        text, re.IGNORECASE,
    )
    knots = num(wind.group(2)) if wind else None
    speed = knots * 1.852 if knots is not None else None
    direction = COMPASS.get(wind.group(1).upper()) if wind else None
    if temp is None and pressure is None and humidity is None:
        raise RuntimeError("ENKA page is missing expected Vantage Pro fields")
    source_time = None
    tm = re.search(r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})", text)
    if tm:
        try:
            source_time = datetime.strptime(tm.group(1) + " " + tm.group(2), "%d/%m/%y %H:%M").replace(tzinfo=ISTANBUL).isoformat()
        except ValueError:
            pass
    return {
        "station_id": "ENKA-BALMUMCU",
        "station_name": "Balmumcu",
        "latitude": 41.1,
        "longitude": 28.9,
        "elevation_m": 107,
        "source": "ENKA · Vantage Pro · w.enka.com/weather",
        "status": "ok",
        "updated_at": source_time,
        "recorded_at": stamp(now),
        "fetched_at": stamp(now),
        "source_time": source_time,
        "current": {
            "temperature": temp,
            "feels_like": feel,
            "humidity": humidity,
            "wind_speed": round(speed, 1) if speed is not None else None,
            "wind_direction": direction,
            "dew_point": dew,
            "rain": rain,
            "pressure": pressure,
            "weather_code": None,
        },
        "error": None,
    }


def parse_run_time(run_int: int) -> datetime:
    return datetime.strptime(str(run_int), "%Y%m%d%H").replace(tzinfo=timezone.utc)


def aggregate_daily(hourly: dict) -> dict:
    groups = defaultdict(lambda: {"temperature": [], "precipitation": [], "wind": []})
    times = hourly.get("time", [])
    for index, value in enumerate(times):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_day = dt.astimezone(ISTANBUL).date().isoformat()
        except (TypeError, ValueError):
            continue
        group = groups[local_day]
        for key, field in (
            ("temperature", "temperature_2m"),
            ("precipitation", "precipitation"),
            ("wind", "wind_speed_10m"),
        ):
            values = hourly.get(field, [])
            item = num(values[index]) if index < len(values) else None
            if item is not None:
                group[key].append(item)
    result = {
        "time": [],
        "temperature_2m_max": [],
        "temperature_2m_min": [],
        "precipitation_sum": [],
        "wind_speed_10m_max": [],
        "weather_code": [],
    }
    for day in sorted(groups):
        group = groups[day]
        result["time"].append(day)
        result["temperature_2m_max"].append(round(max(group["temperature"]), 1) if group["temperature"] else None)
        result["temperature_2m_min"].append(round(min(group["temperature"]), 1) if group["temperature"] else None)
        result["precipitation_sum"].append(round(sum(group["precipitation"]), 1) if group["precipitation"] else None)
        result["wind_speed_10m_max"].append(round(max(group["wind"]), 1) if group["wind"] else None)
        result["weather_code"].append(None)
    return result


def fetch_gfs_run(cycle: str) -> dict:
    """Fetch one GFS cycle from MeteoPT. cycle is '00','06','12' or '18'."""
    url = f"{METEOPT_BASE}?lat={LAT}&lon={LON}&run={cycle}"
    payload = fetch_json(url, timeout=20)
    if payload.get("error"):
        raise RuntimeError(payload.get("message") or "MeteoPT error")
    run_int = payload.get("run")
    if not run_int:
        raise RuntimeError("No run identifier in MeteoPT response")
    run_dt = parse_run_time(run_int)
    steps = payload.get("steps", {}).get("values", [])
    data = payload.get("data", {})
    if not steps or not data:
        raise RuntimeError(f"GFS run {run_int} has no forecast steps")

    times = []
    for hour in steps:
        try:
            times.append((run_dt + timedelta(hours=int(hour))).isoformat().replace("+00:00", "Z"))
        except (TypeError, ValueError):
            times.append(None)

    def series(key: str) -> list:
        values = data.get(key, {}).get("values", [])
        return [num(v) if i < len(values) else None for i, v in enumerate(values)]

    hourly = {
        "time": [t for t in times if t],
        "temperature_2m": series("tmp2m"),
        "precipitation": series("apcp"),
        "wind_speed_10m": series("wind10m"),
        "wind_direction_10m": series("wind10mdir"),
        "temperature_850hPa": series("tmp850mb"),
        "pressure_msl": series("prmsl"),
        "relative_humidity_2m": series("rh2m"),
    }
    valid_len = len(hourly["time"])
    for k in list(hourly.keys()):
        if k != "time":
            hourly[k] = hourly[k][:valid_len]

    required = ("temperature_2m", "precipitation", "wind_speed_10m", "temperature_850hPa", "pressure_msl")
    missing = [k for k in required if not any(v is not None for v in hourly.get(k, [])))]
    if missing:
        raise RuntimeError(f"GFS run {run_int} incomplete; missing usable values for: {', '.join(missing)}")

    return {
        "run": run_dt.strftime("%Y-%m-%dT%H:%MZ"),
        "run_cycle": f"{run_dt.hour:02d}Z",
        "fetched_at": stamp(),
        "model": "NCEP GFS",
        "model_id": "meteopt_gfs",
        "source": "MeteoPT · https://www.meteopt.com/modelos/gfs?lat=41.014&lon=28.950",
        "latitude": 41.014,
        "longitude": 28.950,
        "elevation": payload.get("geodata", {}).get("elevation"),
        "timezone": "Europe/Istanbul",
        "hourly": hourly,
        "daily": aggregate_daily(hourly),
        "hourly_units": {
            "temperature_2m": "°C",
            "precipitation": "mm",
            "wind_speed_10m": "km/h",
            "pressure_msl": "hPa",
            "temperature_850hPa": "°C",
        },
        "daily_units": {
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "precipitation_sum": "mm",
            "wind_speed_10m_max": "km/h",
        },
    }


def collect_gfs(existing: list, now: datetime) -> tuple[list, list]:
    by_run = {item.get("run"): item for item in existing if isinstance(item, dict) and item.get("run")}
    errors = []
    for cycle in ("00", "06", "12", "18"):
        try:
            run = fetch_gfs_run(cycle)
            key = run["run"]
            by_run[key] = run
            print("GFS archive added/updated:", key)
        except Exception as exc:
            message = str(exc)
            errors.append({"cycle": cycle, "error": message[:500]})
            print("GFS cycle", cycle, "unavailable:", message, file=sys.stderr)
    runs = sorted(by_run.values(), key=lambda item: item.get("run", ""), reverse=True)[:4]
    return runs, errors[:6]


def refresh_station(previous: dict, collector, now: datetime, label: str) -> dict:
    try:
        station = collector(now)
        station["history"] = previous.get("history", []) if isinstance(previous, dict) else []
        add_sample(station, now)
        station["history"] = trim_history(station["history"], now)
        print(label + ": OK")
        return station
    except Exception as exc:
        print(label + ": ERROR: " + str(exc), file=sys.stderr)
        stale = dict(previous) if isinstance(previous, dict) else {}
        stale.setdefault("station_name", label)
        stale["status"] = "stale" if stale.get("current") else "unavailable"
        stale["error"] = str(exc)
        stale.setdefault("history", [])
        return stale


def main() -> None:
    now = now_utc()
    dashboard = load_json(DASHBOARD, {"stations": {}, "gfs": {"runs": []}})
    if not isinstance(dashboard, dict):
        dashboard = {"stations": {}, "gfs": {"runs": []}}
    stations = dashboard.setdefault("stations", {})
    stations["mgm"] = refresh_station(stations.get("mgm", {}), collect_mgm, now, "MGM Eyüpsultan 18101")
    stations["enka"] = refresh_station(stations.get("enka", {}), collect_enka, now, "ENKA Balmumcu")

    old_runs = dashboard.get("gfs", {}).get("runs", []) if isinstance(dashboard.get("gfs"), dict) else []
    runs, errors = collect_gfs(old_runs, now)
    dashboard["gfs"] = {
        "status": "ok" if runs else "unavailable",
        "updated_at": stamp(now),
        "source": "MeteoPT · NCEP GFS · api.meteopt.com/gfs/json",
        "requested_coordinates": {"latitude": 41.014, "longitude": 28.95},
        "last_error": errors[0]["error"] if errors else None,
        "recent_errors": errors,
        "runs": runs,
    }
    dashboard["schema_version"] = 1
    dashboard["updated_at"] = stamp(now)
    dashboard["last_poll_at"] = stamp(now)

    save_json(DASHBOARD, dashboard)
    save_json(DATA / "mgm-18101.json", stations["mgm"])
    save_json(DATA / "enka-balmumcu.json", stations["enka"])
    print("Dashboard written. GFS runs:", len(runs))


if __name__ == "__main__":
    main()
