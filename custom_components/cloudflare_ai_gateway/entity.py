"""Base entity for Cloudflare AI Gateway."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
import json
from typing import TYPE_CHECKING, Any

import openai
from openai.types.chat import ChatCompletionMessageParam
import voluptuous as vol
from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.json import json_dumps

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CACHE_TTL,
    CONF_CF_API_TOKEN,
    CONF_CHAT_MODEL,
    CONF_GATEWAY_ID,
    CONF_MAX_TOKENS,
    CONF_PROVIDER,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_PROVIDER,
    DOMAIN,
    LOGGER,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
)

if TYPE_CHECKING:
    from . import CloudflareAIGatewayConfigEntry

# Max number of back and forth with the LLM to generate a response
MAX_TOOL_ITERATIONS = 10


def _format_tool(tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None) -> dict[str, Any]:
    """Format tool specification for Chat Completions API."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
        },
    }


def _convert_content_to_messages(
    chat_content: list[conversation.Content],
) -> list[ChatCompletionMessageParam]:
    """Convert HA chat log content to OpenAI Chat Completions message format."""
    messages: list[ChatCompletionMessageParam] = []

    for content in chat_content:
        if isinstance(content, conversation.ToolResultContent):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": content.tool_call_id,
                    "content": json_dumps(content.tool_result),
                }
            )
            continue

        if content.role == "system":
            messages.append({"role": "system", "content": content.content or ""})
        elif content.role == "user":
            messages.append({"role": "user", "content": content.content or ""})
        elif isinstance(content, conversation.AssistantContent):
            msg: dict[str, Any] = {"role": "assistant"}
            if content.content:
                msg["content"] = content.content
            if content.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                        },
                    }
                    for tc in content.tool_calls
                ]
            messages.append(msg)

    return messages


async def _transform_stream(
    chat_log: conversation.ChatLog,
    response: openai.AsyncStream,
) -> AsyncGenerator[conversation.AssistantContentDeltaDict | conversation.ToolResultContentDeltaDict]:
    """Transform a Chat Completions stream into HA format."""
    started = False
    current_tool_calls: dict[int, dict[str, str]] = {}

    async for chunk in response:
        if not chunk.choices:
            # Final chunk with usage stats
            if chunk.usage:
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                        }
                    }
                )
            continue

        choice = chunk.choices[0]
        delta = choice.delta
        finish_reason = choice.finish_reason

        if not started and (delta.role or delta.content or delta.tool_calls):
            yield {"role": "assistant"}
            started = True

        if delta.content:
            yield {"content": delta.content}

        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": "",
                        "name": "",
                        "arguments": "",
                    }
                if tc_delta.id:
                    current_tool_calls[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        current_tool_calls[idx]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        current_tool_calls[idx]["arguments"] += tc_delta.function.arguments

        if finish_reason == "tool_calls":
            for tc_data in sorted(current_tool_calls.items()):
                try:
                    tool_args = json.loads(tc_data[1]["arguments"])
                except json.JSONDecodeError as err:
                    LOGGER.error(
                        "Failed to parse tool call arguments for '%s': %s",
                        tc_data[1]["name"],
                        err,
                    )
                    raise HomeAssistantError(
                        f"Model returned invalid tool call arguments for '{tc_data[1]['name']}'"
                    ) from err
                yield {
                    "tool_calls": [
                        llm.ToolInput(
                            id=tc_data[1]["id"],
                            tool_name=tc_data[1]["name"],
                            tool_args=tool_args,
                        )
                    ]
                }
            current_tool_calls.clear()
            started = False

        if finish_reason == "length":
            raise HomeAssistantError("Response truncated: max output tokens reached")


def _add_additional_properties_false(schema: dict[str, Any]) -> None:
    """Add additionalProperties: false to all object schemas for strict mode."""
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        for prop in schema.get("properties", {}).values():
            _add_additional_properties_false(prop)
    elif schema.get("type") == "array" and "items" in schema:
        _add_additional_properties_false(schema["items"])


class CloudflareAIGatewayBaseLLMEntity(Entity):
    """Base entity for Cloudflare AI Gateway LLM entities."""

    _attr_has_entity_name = True
    _attr_name: str | None = None

    _client: openai.AsyncOpenAI | None = None

    def __init__(
        self,
        entry: CloudflareAIGatewayConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        provider = subentry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        model = subentry.data[CONF_CHAT_MODEL]
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Cloudflare",
            model=f"{provider}/{model}",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    def _get_client(self) -> openai.AsyncOpenAI:
        """Get or create an OpenAI client configured for the Cloudflare AI Gateway."""
        if self._client is not None:
            return self._client

        entry_data = self.entry.data
        subentry_data = self.subentry.data

        account_id = entry_data[CONF_ACCOUNT_ID]
        gateway_id = entry_data[CONF_GATEWAY_ID]
        cf_api_token = entry_data[CONF_CF_API_TOKEN]

        base_url = f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat"

        extra_headers: dict[str, str] = {}
        if cache_ttl := subentry_data.get(CONF_CACHE_TTL):
            extra_headers["cf-aig-cache-ttl"] = str(cache_ttl)

        self._client = openai.AsyncOpenAI(
            # The CF token authenticates with the gateway via the Authorization
            # header (accepted on the /compat endpoint). For external providers,
            # the gateway injects stored provider keys automatically.
            api_key=cf_api_token,
            base_url=base_url,
            default_headers=extra_headers or None,
            http_client=get_async_client(self.hass),
        )
        return self._client

    def _get_model(self) -> str:
        """Get the model string in provider/model format."""
        provider = self.subentry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        model = self.subentry.data[CONF_CHAT_MODEL]
        return f"{provider}/{model}"

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
        structure: vol.Schema | None = None,
    ) -> None:
        """Generate an answer for the chat log."""
        options = self.subentry.data

        messages = _convert_content_to_messages(chat_log.content)

        model = self._get_model()
        model_args: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            "top_p": options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
            "temperature": options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            "user": chat_log.conversation_id,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if structure:
            schema = convert(structure)
            _add_additional_properties_false(schema)
            model_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": schema,
                },
            }

        if not structure:
            tools: list[dict[str, Any]] = []
            if chat_log.llm_api:
                tools = [_format_tool(tool, chat_log.llm_api.custom_serializer) for tool in chat_log.llm_api.tools]

            if tools:
                model_args["tools"] = tools

        client = self._get_client()

        LOGGER.debug("Calling %s with %d messages", model, len(messages))

        # To prevent infinite loops, we limit the number of iterations
        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                stream = await client.chat.completions.create(**model_args)

                new_content = [
                    content
                    async for content in chat_log.async_add_delta_content_stream(
                        self.entity_id,
                        _transform_stream(chat_log, stream),
                    )
                ]
                messages.extend(_convert_content_to_messages(new_content))
                model_args["messages"] = messages

            except openai.AuthenticationError as err:
                LOGGER.error("Authentication error with Cloudflare AI Gateway: %s", err)
                self.entry.async_start_reauth(self.hass)
                raise HomeAssistantError("Authentication failed. Check your Cloudflare API token") from err
            except openai.NotFoundError as err:
                LOGGER.error("Model not found: %s — %s", model, err)
                raise HomeAssistantError(
                    f"Model '{model}' not found. Check the model name in your configuration"
                ) from err
            except openai.PermissionDeniedError as err:
                LOGGER.error("Permission denied for model %s: %s", model, err)
                raise HomeAssistantError(
                    f"Permission denied for '{model}'. "
                    "Check that your provider API key is configured in Cloudflare AI Gateway"
                ) from err
            except openai.BadRequestError as err:
                LOGGER.error("Bad request for model %s: %s", model, err)
                raise HomeAssistantError(f"Bad request to '{model}': {err.message}") from err
            except openai.RateLimitError as err:
                LOGGER.error("Rate limited: %s", err)
                raise HomeAssistantError("Rate limited by provider") from err
            except openai.APITimeoutError as err:
                LOGGER.error("Request to Cloudflare AI Gateway timed out: %s", err)
                raise HomeAssistantError("Request timed out") from err
            except openai.APIConnectionError as err:
                LOGGER.error("Cannot reach Cloudflare AI Gateway: %s", err)
                raise HomeAssistantError("Cannot reach Cloudflare AI Gateway") from err
            except openai.OpenAIError as err:
                LOGGER.error("Error talking to Cloudflare AI Gateway: %s", err)
                raise HomeAssistantError("Error talking to Cloudflare AI Gateway") from err

            if not chat_log.unresponded_tool_results:
                break
        else:
            LOGGER.warning("Tool call iteration limit (%d) reached", MAX_TOOL_ITERATIONS)
