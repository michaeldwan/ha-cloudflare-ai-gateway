"""The Cloudflare AI Gateway integration."""

from __future__ import annotations

import asyncio

import httpx

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.httpx_client import get_async_client

from .config_flow import ModelNotFound, validate_model
from .const import (
    CONF_ACCOUNT_ID,
    CONF_CF_API_TOKEN,
    CONF_CHAT_MODEL,
    CONF_IMAGE_MODEL,
    DOMAIN,
    LOGGER,
    SUBENTRY_TYPE_AI_TASK_DATA,
    SUBENTRY_TYPE_AI_TASK_IMAGE,
    SUBENTRY_TYPE_CONVERSATION,
    WORKERS_AI_MODEL_PREFIXES,
)

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type CloudflareAIGatewayConfigEntry = ConfigEntry[None]


async def async_setup_entry(hass: HomeAssistant, entry: CloudflareAIGatewayConfigEntry) -> bool:
    """Set up Cloudflare AI Gateway from a config entry."""
    cf_api_token = entry.data[CONF_CF_API_TOKEN]

    # Verify the API token is still valid
    try:
        client = get_async_client(hass)
        resp = await client.get(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers={"Authorization": f"Bearer {cf_api_token}"},
            timeout=10.0,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as err:
        raise ConfigEntryNotReady("Cannot reach Cloudflare API") from err

    if resp.status_code in (401, 403):
        raise ConfigEntryAuthFailed("Invalid Cloudflare API token")
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as err:
        raise ConfigEntryNotReady(f"Cloudflare API returned {resp.status_code}") from err

    result = resp.json()
    if not result.get("success"):
        raise ConfigEntryAuthFailed("Invalid Cloudflare API token")

    # Validate Workers AI models at startup so users get early feedback on typos
    account_id = entry.data[CONF_ACCOUNT_ID]

    async def _validate_subentry_model(subentry_title: str, model: str) -> None:
        try:
            await validate_model(hass, account_id, cf_api_token, model)
        except ModelNotFound:
            LOGGER.error(
                "Model '%s' (subentry '%s') was not found on Cloudflare Workers AI. "
                "Check the model name for typos and reconfigure the model",
                model,
                subentry_title,
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            LOGGER.debug("Could not validate model '%s' (network error)", model)

    validation_tasks: list[asyncio.Task] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_TYPE_AI_TASK_IMAGE:
            model = subentry.data.get(CONF_IMAGE_MODEL, "")
        elif subentry.subentry_type in (SUBENTRY_TYPE_CONVERSATION, SUBENTRY_TYPE_AI_TASK_DATA):
            model = subentry.data.get(CONF_CHAT_MODEL, "")
        else:
            continue

        if model.startswith(WORKERS_AI_MODEL_PREFIXES):
            validation_tasks.append(_validate_subentry_model(subentry.title, model))

    if validation_tasks:
        await asyncio.gather(*validation_tasks)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def _async_entry_updated(hass: HomeAssistant, entry: CloudflareAIGatewayConfigEntry) -> None:
    """Reload the config entry when it is updated (e.g. subentry added/removed)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CloudflareAIGatewayConfigEntry) -> bool:
    """Unload Cloudflare AI Gateway."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
