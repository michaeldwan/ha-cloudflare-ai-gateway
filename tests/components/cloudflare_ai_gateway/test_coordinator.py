"""Tests for Cloudflare AI Gateway analytics coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from custom_components.cloudflare_ai_gateway.coordinator import CloudflareAnalyticsCoordinator
from homeassistant.core import HomeAssistant


def _mock_graphql_response(data=None, errors=None):
    """Create a mock httpx response for a GraphQL call."""
    resp = MagicMock()
    resp.json.return_value = {"data": data, "errors": errors}
    return resp


def _success_data(cost: float = 0.42):
    """Create a successful GraphQL response body."""
    return {
        "viewer": {
            "accounts": [
                {
                    "today": [
                        {
                            "count": 10,
                            "sum": {"cost": cost},
                        }
                    ]
                }
            ]
        }
    }


def _empty_data():
    """Create a response with no data for the window."""
    return {"viewer": {"accounts": [{"today": []}]}}


async def test_coordinator_fetches_cost(hass: HomeAssistant) -> None:
    """Test that the coordinator returns the cost value."""
    with patch(
        "custom_components.cloudflare_ai_gateway.coordinator.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = _mock_graphql_response(data=_success_data(1.23))

        coordinator = CloudflareAnalyticsCoordinator(hass, account_id="acct-id", gateway_id="gw", api_token="token")
        await coordinator.async_refresh()
        assert coordinator.data == 1.23


async def test_coordinator_returns_zero_for_empty_window(hass: HomeAssistant) -> None:
    """Test that an empty result returns 0.0 cost."""
    with patch(
        "custom_components.cloudflare_ai_gateway.coordinator.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = _mock_graphql_response(data=_empty_data())

        coordinator = CloudflareAnalyticsCoordinator(hass, account_id="acct-id", gateway_id="gw", api_token="token")
        await coordinator.async_refresh()
        assert coordinator.data == 0.0


async def test_coordinator_handles_graphql_error(hass: HomeAssistant) -> None:
    """Test that GraphQL errors mark the coordinator as failed."""
    with patch(
        "custom_components.cloudflare_ai_gateway.coordinator.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = _mock_graphql_response(errors=[{"message": "not authorized"}])

        coordinator = CloudflareAnalyticsCoordinator(hass, account_id="acct-id", gateway_id="gw", api_token="token")
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False


async def test_coordinator_handles_network_error(hass: HomeAssistant) -> None:
    """Test that network errors mark the coordinator as failed."""
    with patch(
        "custom_components.cloudflare_ai_gateway.coordinator.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.side_effect = httpx.TimeoutException("timeout")

        coordinator = CloudflareAnalyticsCoordinator(hass, account_id="acct-id", gateway_id="gw", api_token="token")
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False
