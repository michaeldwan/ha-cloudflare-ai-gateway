"""Tests for Cloudflare AI Gateway integration setup."""

from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cloudflare_ai_gateway.const import (
    CONF_CHAT_MODEL,
    CONF_PROVIDER,
    CONF_RECOMMENDED,
    DOMAIN,
    SUBENTRY_TYPE_CONVERSATION,
)
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setting up the integration."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "result": {"status": "active"}}

    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_setup_entry_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup fails when API token is invalid."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": False, "errors": [{"message": "invalid"}]}

    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_http_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup retries when Cloudflare API returns an HTTP error (e.g. 500)."""
    mock_response = httpx.Response(
        status_code=500,
        request=httpx.Request("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify"),
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_http_401_is_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup treats 401 as auth failure, not retry."""
    mock_response = httpx.Response(
        status_code=401,
        request=httpx.Request("GET", "https://api.cloudflare.com/client/v4/user/tokens/verify"),
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup retries when Cloudflare API is unreachable."""
    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.side_effect = httpx.ConnectError("connection failed")
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_timeout(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup retries when Cloudflare API times out."""
    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.side_effect = httpx.TimeoutException("timeout")
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test unloading the integration."""
    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_with_subentries_creates_entities(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that loading with a conversation subentry creates a conversation entity."""
    assert mock_config_entry_with_subentries.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, mock_config_entry_with_subentries.entry_id)
    assert len(entities) == 6  # 1 conversation + 5 sensors
    domains = {e.domain for e in entities}
    assert domains == {"conversation", "sensor"}


async def test_subentry_added_reloads_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that adding a subentry to a loaded entry triggers a reload."""
    assert mock_config_entry.state is ConfigEntryState.LOADED

    # No entities for our integration yet
    entity_registry = er.async_get(hass)
    assert not er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)

    with patch(
        "custom_components.cloudflare_ai_gateway.get_async_client",
    ) as mock_get_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "result": {"status": "active"}}
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response

        hass.config_entries.async_add_subentry(
            mock_config_entry,
            ConfigSubentry(
                data=MappingProxyType(
                    {
                        CONF_RECOMMENDED: True,
                        CONF_PROVIDER: "openai",
                        CONF_CHAT_MODEL: "gpt-4o-mini",
                    }
                ),
                subentry_type=SUBENTRY_TYPE_CONVERSATION,
                title="Test Model",
                unique_id=None,
            ),
        )
        await hass.async_block_till_done()

    # After reload, the new conversation subentry's entity should exist
    assert mock_config_entry.state is ConfigEntryState.LOADED
    entities = er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)
    assert len(entities) == 6  # 1 conversation + 5 sensors


async def test_device_created_per_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that each subentry creates a device."""
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, mock_config_entry_with_subentries.entry_id)

    assert len(devices) == 1
    device = devices[0]
    assert device.manufacturer == "Cloudflare"
    assert device.model == "openai/gpt-4o-mini"
    assert device.entry_type is dr.DeviceEntryType.SERVICE

    subentry = next(iter(mock_config_entry_with_subentries.subentries.values()))
    assert (DOMAIN, subentry.subentry_id) in device.identifiers
