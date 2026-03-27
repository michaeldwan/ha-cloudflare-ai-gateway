"""DataUpdateCoordinator for Cloudflare AI Gateway analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
POLL_INTERVAL = timedelta(minutes=5)


def _build_query(account_id: str, gateway_id: str, start: str, end: str) -> str:
    """Build the GraphQL query for gateway analytics."""
    return (
        "{ viewer { accounts(filter: { accountTag: "
        f'"{account_id}"'
        " }) { today: aiGatewayRequestsAdaptiveGroups("
        "limit: 1, filter: { "
        f'datetimeHour_geq: "{start}", '
        f'datetimeHour_leq: "{end}", '
        f'gateway: "{gateway_id}"'
        " }) { count sum { cost } } } } }"
    )


class CloudflareAnalyticsCoordinator(DataUpdateCoordinator[float | None]):
    """Coordinator that polls CF GraphQL for gateway cost today."""

    def __init__(
        self,
        hass: HomeAssistant,
        account_id: str,
        gateway_id: str,
        api_token: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_analytics",
            update_interval=POLL_INTERVAL,
        )
        self._account_id = account_id
        self._gateway_id = gateway_id
        self._api_token = api_token

    async def _async_update_data(self) -> float | None:
        """Fetch cost today from the GraphQL API."""
        # Use user's local midnight converted to UTC so "today" matches their timezone
        local_start = dt_util.start_of_local_day()
        start_str = local_start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = _build_query(self._account_id, self._gateway_id, start_str, now_str)

        client = get_async_client(self.hass)
        try:
            resp = await client.post(
                GRAPHQL_URL,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
                json={"query": query},
                timeout=10.0,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as err:
            raise UpdateFailed("Cannot reach Cloudflare API") from err

        try:
            result: dict[str, Any] = resp.json()
        except ValueError as err:
            raise UpdateFailed(f"Invalid response from Cloudflare API: {resp.status_code}") from err

        if errors := result.get("errors"):
            raise UpdateFailed(f"GraphQL error: {errors[0].get('message', 'unknown')}")

        try:
            groups = result["data"]["viewer"]["accounts"][0]["today"]
            if not groups:
                return 0.0
            return groups[0]["sum"]["cost"]
        except (KeyError, IndexError, TypeError) as err:
            raise UpdateFailed(f"Unexpected response shape: {err}") from err
