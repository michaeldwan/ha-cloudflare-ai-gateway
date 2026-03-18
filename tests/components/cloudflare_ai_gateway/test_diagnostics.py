"""Tests for Cloudflare AI Gateway diagnostics."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cloudflare_ai_gateway.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant


async def test_diagnostics_redacts_sensitive_data(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that diagnostics redacts sensitive fields."""
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry_with_subentries)

    assert result["data"]["cf_api_token"] == REDACTED
    assert result["data"]["account_id"] == REDACTED
    assert result["data"]["gateway_id"] == REDACTED
