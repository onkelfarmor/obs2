"""MinForsyning consumption API client."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp

from .auth import AuthenticationError, MinForsyningAuth
from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

# Candidate API endpoints tried in order
_CONSUMPTION_ENDPOINTS = [
    "/api/consumption/period",
    "/api/v1/consumption/period",
    "/api/consumption",
    "/api/v1/consumption",
    "/pluginapi/v1/consumption",
    "/pluginapi/consumption",
    "/api/metering/consumption",
]

_INSTALLATION_ENDPOINTS = [
    "/api/installations",
    "/api/v1/installations",
    "/api/metering/installations",
    "/pluginapi/v1/installations",
]


class ConsumptionData:
    """Parsed consumption data ready for HA sensors."""

    def __init__(self) -> None:
        self.daily_values: dict[str, float] = {}  # ISO date → m³
        self.today: float = 0.0
        self.yesterday: float = 0.0
        self.month_total: float = 0.0
        self.year_total: float = 0.0
        self.unit: str = "m³"
        self.meter_id: str | None = None

    def aggregate(self) -> None:
        """Compute rolling aggregates from daily_values."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        month_total = 0.0
        year_total = 0.0

        for iso, val in self.daily_values.items():
            try:
                d = date.fromisoformat(iso)
            except ValueError:
                continue
            if d == today:
                self.today = val
            if d == yesterday:
                self.yesterday = val
            if d >= month_start:
                month_total += val
            if d >= year_start:
                year_total += val

        self.month_total = round(month_total, 3)
        self.year_total = round(year_total, 3)


class MinForsyningAPI:
    """Fetch water consumption from the MinForsyning API."""

    def __init__(self, session: aiohttp.ClientSession, auth: MinForsyningAuth) -> None:
        self._session = session
        self._auth = auth
        self._working_endpoint: str | None = None

    async def _headers(self) -> dict[str, str]:
        token = await self._auth.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def fetch_consumption(self, days_back: int = 365) -> ConsumptionData:
        """Return consumption data for the last *days_back* days."""
        today = date.today()
        from_date = today - timedelta(days=days_back)

        headers = await self._headers()

        # Use previously discovered endpoint first
        if self._working_endpoint:
            data = await self._try_endpoint(
                self._working_endpoint, headers, from_date, today
            )
            if data is not None:
                return data

        # Probe candidate endpoints
        for ep in _CONSUMPTION_ENDPOINTS:
            _LOGGER.debug("Trying consumption endpoint: %s", ep)
            data = await self._try_endpoint(ep, headers, from_date, today)
            if data is not None:
                self._working_endpoint = ep
                _LOGGER.info("MinForsyning: using consumption endpoint %s", ep)
                return data

        # Fall back: discover via installations endpoint
        data = await self._try_via_installations(headers, from_date, today)
        if data is not None:
            return data

        raise RuntimeError(
            "Could not find a working consumption endpoint. "
            "Enable debug logging for minforsyning to see full responses."
        )

    async def _try_endpoint(
        self,
        endpoint: str,
        headers: dict,
        from_date: date,
        to_date: date,
    ) -> ConsumptionData | None:
        url = API_BASE_URL + endpoint
        params = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
        }
        try:
            async with self._session.get(
                url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status in (404, 405):
                    return None
                if resp.status == 401:
                    raise AuthenticationError("API returned 401 – token may be invalid")
                if resp.status != 200:
                    _LOGGER.debug("Endpoint %s returned %s", endpoint, resp.status)
                    return None

                raw = await resp.json(content_type=None)
                _LOGGER.debug("Endpoint %s response (truncated): %s", endpoint, str(raw)[:500])
                return self._parse(raw)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Endpoint %s error: %s", endpoint, err)
            return None

    async def _try_via_installations(
        self, headers: dict, from_date: date, to_date: date
    ) -> ConsumptionData | None:
        for ep in _INSTALLATION_ENDPOINTS:
            url = API_BASE_URL + ep
            try:
                async with self._session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        continue
                    installations = await resp.json(content_type=None)
                    _LOGGER.debug("Installations response: %s", str(installations)[:500])
            except (aiohttp.ClientError, TimeoutError):
                continue

            inst_id = self._extract_installation_id(installations)
            if not inst_id:
                continue

            for consumption_path in [
                f"{ep}/{inst_id}/consumption",
                f"/api/consumption/installation/{inst_id}",
                f"/api/v1/consumption/installation/{inst_id}",
            ]:
                data = await self._try_endpoint(consumption_path, headers, from_date, to_date)
                if data is not None:
                    data.meter_id = str(inst_id)
                    self._working_endpoint = consumption_path
                    return data

        return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self, raw: Any) -> ConsumptionData | None:
        result = ConsumptionData()

        # Unwrap common envelope shapes
        items: list[dict] = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            for key in ("data", "values", "consumption", "items", "results", "readings"):
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break
            if not items:
                # Single-item dict
                items = [raw]

        if not items:
            return None

        for item in items:
            if not isinstance(item, dict):
                continue
            d = self._extract_date(item)
            v = self._extract_value(item)
            if d is not None and v is not None:
                result.daily_values[d.isoformat()] = v

            # Try to detect unit
            for unit_key in ("unit", "Unit", "enhed"):
                if unit_key in item:
                    raw_unit = str(item[unit_key]).lower()
                    if "liter" in raw_unit or raw_unit == "l":
                        result.unit = "L"
                    elif "m3" in raw_unit or "m³" in raw_unit:
                        result.unit = "m³"

        if not result.daily_values:
            return None

        result.aggregate()
        return result

    @staticmethod
    def _extract_date(item: dict) -> date | None:
        for key in ("date", "Date", "day", "Day", "from", "From", "period", "Period",
                    "timestamp", "Timestamp", "dateTime", "DateTime", "readingDate"):
            val = item.get(key)
            if val:
                try:
                    return datetime.fromisoformat(str(val)[:10]).date()
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _extract_value(item: dict) -> float | None:
        for key in ("value", "Value", "consumption", "Consumption",
                    "amount", "Amount", "quantity", "Quantity",
                    "usage", "Usage", "reading", "Reading", "volume", "Volume"):
            val = item.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _extract_installation_id(data: Any) -> Any:
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return None
        for key in ("id", "Id", "installationId", "InstallationId",
                    "meterId", "MeterId", "installationNumber"):
            if key in item:
                return item[key]
        return None
