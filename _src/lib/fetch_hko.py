#!/usr/bin/env python3
"""Fetch today's Hong Kong weather from official HKO sources and write the JSON
consumed by render_card.py.

Sources (all Hong Kong Observatory):
  current   : data.weather.gov.hk  dataType=rhrread  (HKO station temp, humidity, icon)
  today     : dataType=flw (local forecast), dataType=fnd (9-day: max/min, wind, PSR)
  warnings  : dataType=warnsum (+ warningInfo for the text)
  hourly    : maps.weather.gov.hk/ocf/dat/<STATION>.xml  -- HKO "Location-specific
              forecast" (Objective Consensus Forecast). Despite the .xml name it is JSON.
              Gives real HOURLY temperature / RH / wind, a weather-icon code every
              3 hours, and a DAILY chance of rain (no hourly rain probability exists).

Nothing is invented: any field that isn't available is null, and every slot records
where each value came from.

Usage: python3 fetch_hko.py [-o out.json] [--station HKO] [--date YYYY-MM-DD]
"""
import argparse, json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone

HKT = timezone(timedelta(hours=8))
API = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType={}&lang=en"
OCF = "https://maps.weather.gov.hk/ocf/dat/{}.xml"
SLOT_HOURS = [7, 10, 13, 16, 19, 21]

# HKO weather icon codes -> short English label (https://www.hko.gov.hk/textonly/v2/explain/wxicon_e.htm)
ICON_LABEL = {
    50: "Sunny", 51: "Sunny periods", 52: "Sunny intervals",
    53: "Sunny periods, showers", 54: "Sunny intervals, showers",
    60: "Cloudy", 61: "Overcast", 62: "Light rain", 63: "Rain", 64: "Heavy rain",
    65: "Thunderstorms", 70: "Fine", 71: "Fine", 72: "Fine", 73: "Fine", 74: "Fine",
    75: "Fine", 76: "Mainly cloudy", 77: "Mainly fine", 80: "Windy", 81: "Dry",
    82: "Humid", 83: "Fog", 84: "Mist", 85: "Haze", 90: "Hot", 91: "Warm",
    92: "Cool", 93: "Cold",
}


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 hk-weather-card"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def safe(fn, errors, name):
    try:
        return fn()
    except Exception as e:  # keep going; renderer degrades gracefully
        errors.append(f"{name}: {e}")
        return None


def norm_code(code):
    if code is None:
        return None
    code = int(code)
    if code not in ICON_LABEL and code >= 100:  # OCF occasionally emits e.g. 741
        code = int(str(code)[:2])
    return code if code in ICON_LABEL else None


def short_wind(text):
    """'East force 2 to 3.' -> 'E force 2–3'"""
    if not text:
        return None
    t = text.strip().rstrip(".")
    dirs = {"north": "N", "south": "S", "east": "E", "west": "W"}
    def repl_dir(m):
        return "".join(dirs[p] for p in re.split(r"[\s-]+", m.group(0).lower()) if p in dirs)
    t = re.sub(r"\b(north|south)?[\s-]?(east|west)?\b(?= force)|\b(north|south|east|west)(?=\s)",
               lambda m: repl_dir(m) if m.group(0).strip() else m.group(0), t, count=1, flags=re.I)
    t = re.sub(r"(\d)\s+to\s+(\d)", "\\1–\\2", t)
    return t.strip()


def first_sentences(text, n=2):
    if not text:
        return None
    parts = [p.strip() for p in re.split(r"(?<=\.)\s+", text.strip()) if p.strip()]
    return " ".join(parts[:n])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="-")
    ap.add_argument("--station", default="HKO", help="OCF station code (HKO = Observatory, Tsim Sha Tsui)")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today HKT)")
    ap.add_argument("--view", default=None, help="optional background view name to embed")
    a = ap.parse_args()

    now = datetime.now(HKT)
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else now.date()
    ymd = day.strftime("%Y%m%d")
    errors = []

    rhr = safe(lambda: get_json(API.format("rhrread")), errors, "rhrread") or {}
    flw = safe(lambda: get_json(API.format("flw")), errors, "flw") or {}
    fnd = safe(lambda: get_json(API.format("fnd")), errors, "fnd") or {}
    wsum = safe(lambda: get_json(API.format("warnsum")), errors, "warnsum") or {}
    winfo = safe(lambda: get_json(API.format("warningInfo")), errors, "warningInfo") or {}
    ocf = safe(lambda: get_json(OCF.format(a.station)), errors, f"ocf/{a.station}") or {}

    # ---- current ----
    temp_now = next((t["value"] for t in rhr.get("temperature", {}).get("data", [])
                     if t.get("place") == "Hong Kong Observatory"), None)
    rh_now = next((h["value"] for h in rhr.get("humidity", {}).get("data", [])
                   if h.get("place") == "Hong Kong Observatory"), None)
    icon_now = norm_code((rhr.get("icon") or [None])[0])
    uv = (rhr.get("uvindex") or {}).get("data") if isinstance(rhr.get("uvindex"), dict) else None

    # ---- today (9-day forecast entry for the date) ----
    today = next((f for f in fnd.get("weatherForecast", []) if f.get("forecastDate") == ymd), {})
    ocf_day = next((f for f in ocf.get("DailyForecast", []) if f.get("ForecastDate") == ymd), {})
    hi = (today.get("forecastMaxtemp") or {}).get("value")
    lo = (today.get("forecastMintemp") or {}).get("value")
    hi_src = lo_src = "HKO 9-day forecast (fnd)"
    if hi is None and ocf_day.get("ForecastMaximumTemperature") is not None:
        hi, hi_src = round(ocf_day["ForecastMaximumTemperature"]), f"HKO OCF daily ({a.station})"
    if lo is None and ocf_day.get("ForecastMinimumTemperature") is not None:
        lo, lo_src = round(ocf_day["ForecastMinimumTemperature"]), f"HKO OCF daily ({a.station})"

    # ---- hourly slots from OCF ----
    hourly = {h["ForecastHour"]: h for h in ocf.get("HourlyWeatherForecast", [])}
    coded = {int(k[8:10]): norm_code(v["ForecastWeather"]) for k, v in hourly.items()
             if k.startswith(ymd) and v.get("ForecastWeather") is not None and norm_code(v["ForecastWeather"])}
    slots = []
    for hr in SLOT_HOURS:
        h = hourly.get(f"{ymd}{hr:02d}")
        if not h:
            continue
        code, code_hr = None, None
        if coded:
            code_hr = min(coded, key=lambda c: (abs(c - hr), c))
            if abs(code_hr - hr) <= 2:
                code = coded[code_hr]
            else:
                code_hr = None
        slots.append({
            "hour": hr,
            "label": (f"{hr % 12 or 12}{'am' if hr < 12 else 'pm'}"),
            "temp": round(h["ForecastTemperature"]) if h.get("ForecastTemperature") is not None else None,
            "temp_source": f"HKO OCF hourly ({a.station}) {hr:02d}:00",
            "weather_code": code,
            "weather": ICON_LABEL.get(code) if code else None,
            "weather_source": (f"HKO OCF 3-hourly weather code at {code_hr:02d}:00" if code else None),
            "rain_pct": None,  # HKO publishes no hourly rain probability
            "rain_source": None,
            "humidity": round(h["ForecastRelativeHumidity"]) if h.get("ForecastRelativeHumidity") is not None else None,
        })

    # ---- warnings ----
    details = {d.get("subtype") or d.get("warningStatementCode"): " ".join(d.get("contents", []))
               for d in winfo.get("details", [])}
    warnings = []
    for key, w in (wsum or {}).items():
        if not isinstance(w, dict) or w.get("actionCode") == "CANCEL":
            continue
        name, wtype, code = w.get("name", key), w.get("type"), w.get("code", key)
        if key == "WTCSGNL":
            m = re.match(r"TC(\d+)", code or "")
            title = f"No. {m.group(1)} Signal" if m else name
            title = f"{title} · {name.replace(' Warning Signal', '')}" if m else title
        elif wtype and wtype.lower() not in name.lower():
            title = f"{wtype} {name}"
        else:
            title = name
        warnings.append({"key": key, "code": code, "type": wtype, "title": title,
                         "detail": details.get(code) or details.get(key)})

    out = {
        "schema": 1,
        "place": "Hong Kong",
        "date": day.isoformat(),
        "date_label": day.strftime("%a %-d %b"),
        "generated_at": now.isoformat(timespec="minutes"),
        "current": {
            "temp": temp_now, "temp_source": "HKO rhrread · Hong Kong Observatory station",
            "humidity": rh_now, "weather_code": icon_now,
            "condition": ICON_LABEL.get(icon_now) if icon_now else None,
            "uv": uv[0]["value"] if uv else None,
            "updated": rhr.get("updateTime"),
        },
        "today": {
            "high": hi, "low": lo, "high_source": hi_src, "low_source": lo_src,
            "summary": first_sentences(today.get("forecastWeather") or flw.get("forecastDesc"), 3),
            "local_forecast": flw.get("forecastDesc"),
            "wind": short_wind(today.get("forecastWind")), "wind_raw": today.get("forecastWind"),
            "psr": today.get("PSR"),
            "chance_of_rain": ocf_day.get("ForecastChanceOfRain"),
            "chance_of_rain_source": f"HKO OCF daily chance of rain ({a.station})" if ocf_day.get("ForecastChanceOfRain") else None,
            "weather_code": norm_code(today.get("ForecastIcon")),
        },
        "hourly": slots,
        "hourly_source": (f"HKO location-specific forecast (OCF) {OCF.format(a.station)} "
                          f"LastModified={ocf.get('LastModified')}: hourly temperature is real hourly model "
                          f"output; icons use the nearest 3-hourly weather code; no hourly rain probability published."
                          if slots else None),
        "warnings": warnings,
        "tc_info": flw.get("tcInfo") or None,
        "view": a.view,
        "errors": errors,
    }
    s = json.dumps(out, ensure_ascii=False, indent=2)
    if a.out == "-":
        print(s)
    else:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(s + "\n")
        print(f"wrote {a.out} ({len(slots)} hourly slots, {len(warnings)} warnings, {len(errors)} errors)", file=sys.stderr)


if __name__ == "__main__":
    main()
