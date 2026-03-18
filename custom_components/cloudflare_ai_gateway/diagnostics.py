"""Diagnostics support for Cloudflare AI Gateway."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {"cf_api_token", "account_id", "gateway_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return async_redact_data(
        {
            "title": entry.title,
            "data": dict(entry.data),
            "subentries": [
                {
                    "title": subentry.title,
                    "type": subentry.subentry_type,
                    "data": dict(subentry.data),
                }
                for subentry in entry.subentries.values()
            ],
        },
        TO_REDACT,
    )
