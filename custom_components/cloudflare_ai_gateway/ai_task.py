"""AI Task support for Cloudflare AI Gateway."""

from __future__ import annotations

import base64
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any

import httpx

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.util.json import json_loads

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CF_API_TOKEN,
    CONF_GATEWAY_ID,
    CONF_IMAGE_HEIGHT,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_STEPS,
    CONF_IMAGE_WIDTH,
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_STEPS,
    DEFAULT_IMAGE_WIDTH,
    DOMAIN,
    LOGGER,
    SUBENTRY_TYPE_AI_TASK_DATA,
    SUBENTRY_TYPE_AI_TASK_IMAGE,
)
from .entity import CloudflareAIGatewayBaseLLMEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

    from . import CloudflareAIGatewayConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CloudflareAIGatewayConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_TYPE_AI_TASK_DATA:
            async_add_entities(
                [CloudflareAIGatewayDataTaskEntity(config_entry, subentry)],
                config_subentry_id=subentry.subentry_id,
            )
        elif subentry.subentry_type == SUBENTRY_TYPE_AI_TASK_IMAGE:
            async_add_entities(
                [CloudflareAIGatewayImageTaskEntity(config_entry, subentry)],
                config_subentry_id=subentry.subentry_id,
            )


class CloudflareAIGatewayDataTaskEntity(
    ai_task.AITaskEntity,
    CloudflareAIGatewayBaseLLMEntity,
):
    """Cloudflare AI Gateway data generation task entity."""

    _attr_supported_features = ai_task.AITaskEntityFeature.GENERATE_DATA

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        LOGGER.debug(
            "Generating data for task '%s' with model %s (structured=%s)",
            task.name,
            self._get_model(),
            task.structure is not None,
        )
        await self._async_handle_chat_log(chat_log, task.structure)

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            raise HomeAssistantError("Error getting response from Cloudflare AI Gateway")

        text = chat_log.content[-1].content or ""

        if not task.structure:
            LOGGER.debug("Data task '%s' completed with plain text response", task.name)
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )

        try:
            data: Any = json_loads(text)
        except JSONDecodeError as err:
            LOGGER.error("Failed to parse JSON response: %s. Response: %s", err, text)
            raise HomeAssistantError("Error getting response from Cloudflare AI Gateway") from err

        LOGGER.debug("Data task '%s' completed with structured response", task.name)
        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )


class CloudflareAIGatewayImageTaskEntity(
    ai_task.AITaskEntity,
):
    """Cloudflare AI Gateway image generation task entity."""

    _attr_has_entity_name = True
    _attr_name: str | None = None
    _attr_supported_features = ai_task.AITaskEntityFeature.GENERATE_IMAGE

    def __init__(
        self,
        entry: CloudflareAIGatewayConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        model = subentry.data.get(CONF_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Cloudflare",
            model=f"workers-ai/{model}",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task."""
        entry_data = self.entry.data
        subentry_data = self.subentry.data

        account_id = entry_data[CONF_ACCOUNT_ID]
        gateway_id = entry_data[CONF_GATEWAY_ID]
        cf_api_token = entry_data[CONF_CF_API_TOKEN]

        model = subentry_data.get(CONF_IMAGE_MODEL, DEFAULT_IMAGE_MODEL)
        width = int(subentry_data.get(CONF_IMAGE_WIDTH, DEFAULT_IMAGE_WIDTH))
        height = int(subentry_data.get(CONF_IMAGE_HEIGHT, DEFAULT_IMAGE_HEIGHT))
        steps = int(subentry_data.get(CONF_IMAGE_STEPS, DEFAULT_IMAGE_STEPS))

        url = f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/workers-ai/{model}"

        LOGGER.debug(
            "Generating image: model=%s, %dx%d, %d steps, prompt='%s'",
            model,
            width,
            height,
            steps,
            task.instructions[:100],
        )

        client = get_async_client(self.hass)
        try:
            response = await client.post(
                url,
                # Workers AI via gateway requires both headers:
                # cf-aig-authorization for gateway auth, Authorization for provider auth
                headers={
                    "cf-aig-authorization": f"Bearer {cf_api_token}",
                    "Authorization": f"Bearer {cf_api_token}",
                },
                json={
                    "prompt": task.instructions,
                    "width": width,
                    "height": height,
                    "num_steps": steps,
                },
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            status = err.response.status_code
            if status == 401:
                LOGGER.error("Authentication failed for image generation: %s", err)
                self.entry.async_start_reauth(self.hass)
                raise HomeAssistantError("Authentication failed. Check your Cloudflare API token") from err
            if status == 403:
                LOGGER.error("Permission denied for image model %s: %s", model, err)
                raise HomeAssistantError(
                    f"Permission denied for '{model}'. Check that your API token has the required permissions"
                ) from err
            if status == 404:
                LOGGER.error("Image model not found: %s — %s", model, err)
                raise HomeAssistantError(
                    f"Model '{model}' not found. Check the model name in your configuration"
                ) from err
            detail = ""
            try:
                body = err.response.json()
                errors = body.get("errors", [])
                if errors:
                    detail = ": " + "; ".join(e.get("message", str(e)) for e in errors)
            except Exception:  # noqa: BLE001
                pass
            LOGGER.error("Error generating image (HTTP %s)%s", status, detail or f": {err}")
            raise HomeAssistantError(f"Error generating image{detail or ' via Cloudflare AI Gateway'}") from err
        except (httpx.ConnectError, httpx.TimeoutException) as err:
            LOGGER.error("Connection error generating image: %s", err)
            raise HomeAssistantError("Cannot reach Cloudflare AI Gateway") from err

        try:
            result = response.json()
        except ValueError as err:
            LOGGER.error("Failed to parse image response: %s", err)
            raise HomeAssistantError("Invalid response from Cloudflare AI Gateway") from err

        image_b64 = result.get("result", {}).get("image")
        if not image_b64:
            LOGGER.error("No image in response: %s", result)
            raise HomeAssistantError("No image returned from Cloudflare AI Gateway")

        image_data = base64.b64decode(image_b64)
        LOGGER.debug("Image generated successfully: %d bytes", len(image_data))

        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=self.entity_id,
                content=f"Generated image with {model}",
            )
        )

        return ai_task.GenImageTaskResult(
            image_data=image_data,
            conversation_id=chat_log.conversation_id,
            mime_type="image/png",
            width=width,
            height=height,
            model=model,
        )
