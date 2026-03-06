"""API Toolkit — external service integrations.

Provides HTTP-based tools for interacting with third-party APIs.  Each
integration is a separate tool class so the LLM can pick the right one.

Currently implements:
  - Generic HTTP request (GET/POST)
  - Weather lookup (Open-Meteo, no API key needed)

Additional integrations (Gmail, Calendar, etc.) can be added by
subclassing ``BaseTool`` and registering with the ``ToolRegistry``.
"""

from __future__ import annotations

import json

import httpx

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)

_HTTP_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Generic HTTP Request
# ---------------------------------------------------------------------------
class ApiHttpRequest(BaseTool):
    name = "api_http_request"
    description = (
        "Make an HTTP request (GET or POST) to any URL and return the response. "
        "Use for generic API calls."
    )

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", "query", default=""))
        method = str(self._first_param(params, "method", default="GET")).upper()
        headers = params.get("headers", {})
        body = self._first_param(params, "body", "data", "content", default=None)

        if not url:
            return self._failure("No URL provided")

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, verify=False) as client:
                if method == "POST":
                    response = await client.post(url, json=body, headers=headers)
                else:
                    response = await client.get(url, headers=headers)

                # Truncate large response bodies.
                max_chars = params.get("max_chars", 10_000)
                text = response.text[:max_chars]

                logger.info(
                    "api.http_request",
                    method=method,
                    url=url,
                    status=response.status_code,
                )
                return self._success(
                    f"{method} {url} -> {response.status_code}",
                    data={
                        "status_code": response.status_code,
                        "body": text,
                        "headers": dict(response.headers),
                    },
                )
        except Exception as exc:
            return self._failure(f"HTTP request failed: {exc}")


# ---------------------------------------------------------------------------
# Weather Lookup (Open-Meteo — free, no key)
# ---------------------------------------------------------------------------
class ApiWeather(BaseTool):
    name = "api_weather"
    description = (
        "Get current weather for a latitude/longitude using Open-Meteo (free, no API key)."
    )

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        lat = self._first_param(params, "latitude", "lat")
        lon = self._first_param(params, "longitude", "lon")
        if lat is None or lon is None:
            return self._failure("latitude and longitude are required")

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,wind_speed_10m,relative_humidity_2m,weather_code"
                f"&timezone=auto"
            )
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, verify=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                current = data.get("current", {})

                weather = {
                    "temperature_c": current.get("temperature_2m"),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "weather_code": current.get("weather_code"),
                    "timezone": data.get("timezone"),
                }
                summary = (
                    f"{weather['temperature_c']}°C, "
                    f"wind {weather['wind_speed_kmh']} km/h, "
                    f"humidity {weather['humidity_percent']}%"
                )
                logger.info("api.weather", lat=lat, lon=lon)
                return self._success(summary, data=weather)
        except Exception as exc:
            return self._failure(f"Weather lookup failed: {exc}")


# ---------------------------------------------------------------------------
# Datetime / Timezone
# ---------------------------------------------------------------------------
class ApiDatetime(BaseTool):
    name = "api_datetime"
    description = "Get the current date and time, optionally for a specific timezone."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from datetime import datetime, timezone
        import zoneinfo

        default_tz = "Europe/Istanbul"
        params = self._params(tool_input)
        tz_name = self._first_param(params, "timezone", "tz", default=default_tz) or default_tz
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            try:
                tz_name = default_tz
                tz = zoneinfo.ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc
                tz_name = "UTC"

        now = datetime.now(tz)
        return self._success(
            now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            data={
                "iso": now.isoformat(),
                "timezone": tz_name,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
            },
        )
