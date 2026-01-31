import os
import time
import requests
from flask import Blueprint, request, jsonify

weather_bp = Blueprint("weather", __name__)

# Simple in-memory cache (good enough for dev / single process)
# key -> (expires_at, data)
_CACHE = {}
CACHE_TTL_SEC = int(os.getenv("WEATHER_CACHE_TTL", "60"))  # cache 60s by default

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    expires_at, data = item
    if time.time() > expires_at:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data):
    _CACHE[key] = (time.time() + CACHE_TTL_SEC, data)


def _require_api_key():
    if not OPENWEATHER_API_KEY:
        return jsonify({
            "error": "OPENWEATHER_API_KEY is not set",
            "hint": "export OPENWEATHER_API_KEY=your_key or put in .env"
        }), 500
    return None


def _normalize_openweather(payload: dict) -> dict:
    """Return a stable, frontend-friendly shape."""
    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    clouds = payload.get("clouds") or {}
    sys = payload.get("sys") or {}

    return {
        "location": {
            "name": payload.get("name"),
            "country": sys.get("country"),
            "lat": (payload.get("coord") or {}).get("lat"),
            "lon": (payload.get("coord") or {}).get("lon"),
            "timezone": payload.get("timezone"),
        },
        "weather": {
            "main": weather.get("main"),
            "description": weather.get("description"),
            "icon": weather.get("icon"),  # e.g. "10d"
            "id": weather.get("id"),
        },
        "temp": {
            "current": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "min": main.get("temp_min"),
            "max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
        },
        "wind": {
            "speed": wind.get("speed"),
            "deg": wind.get("deg"),
            "gust": wind.get("gust"),
        },
        "clouds": {
            "all": clouds.get("all"),
        },
        "rain": payload.get("rain"),  # may be None
        "snow": payload.get("snow"),  # may be None
        "visibility": payload.get("visibility"),
        "dt": payload.get("dt"),
        "sun": {
            "sunrise": sys.get("sunrise"),
            "sunset": sys.get("sunset"),
        },
        "raw": payload,  # keep full response in case you need more later
    }


@weather_bp.get("", strict_slashes=False)
def get_weather():
    """
    GET /api/weather?lat=27.7172&lon=85.3240&units=metric
    or
    GET /api/weather?city=Kathmandu&units=metric

    units: standard | metric | imperial (default: metric)
    """
    api_key_err = _require_api_key()
    if api_key_err:
        return api_key_err

    units = request.args.get("units", "metric")
    if units not in ("standard", "metric", "imperial"):
        return jsonify({"error": "units must be one of: standard, metric, imperial"}), 400

    lat = request.args.get("lat")
    lon = request.args.get("lon")
    city = request.args.get("city")

    params = {"appid": OPENWEATHER_API_KEY, "units": units}

    if lat and lon:
        params["lat"] = lat
        params["lon"] = lon
        cache_key = f"latlon:{lat},{lon}|units:{units}"
    elif city:
        params["q"] = city
        cache_key = f"city:{city.lower()}|units:{units}"
    else:
        return jsonify({"error": "Provide either lat & lon, or city"}), 400

    cached = _cache_get(cache_key)
    if cached:
        return jsonify({"ok": True, "cached": True, **cached}), 200

    try:
        resp = requests.get(OPENWEATHER_BASE, params=params, timeout=10)
        # OpenWeather uses JSON error bodies too
        data = resp.json()
    except requests.RequestException as e:
        return jsonify({"error": "weather_upstream_failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "invalid_weather_response", "details": str(e)}), 502

    if resp.status_code != 200:
        # Example: 401 invalid key, 404 city not found
        return jsonify({
            "error": "weather_api_error",
            "status_code": resp.status_code,
            "upstream": data,
        }), 502

    normalized = _normalize_openweather(data)
    payload = {"data": normalized}

    _cache_set(cache_key, payload)
    return jsonify({"ok": True, "cached": False, **payload}), 200
