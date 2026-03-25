"""Config flow for Cloudflare AI Gateway integration."""

from __future__ import annotations

from typing import Any

import httpx
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_LLM_HASS_API, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.typing import VolDictType

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CACHE_TTL,
    CONF_CF_API_TOKEN,
    CONF_CHAT_MODEL,
    CONF_GATEWAY_ID,
    CONF_IMAGE_HEIGHT,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_STEPS,
    CONF_IMAGE_WIDTH,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_PROVIDER,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_AI_TASK_DATA_MODEL,
    DEFAULT_CONVERSATION_MODEL,
    DEFAULT_GATEWAY_ID,
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_STEPS,
    DEFAULT_IMAGE_WIDTH,
    DEFAULT_PROVIDER,
    DOMAIN,
    LOGGER,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    SUBENTRY_TYPE_AI_TASK_DATA,
    SUBENTRY_TYPE_AI_TASK_IMAGE,
    SUBENTRY_TYPE_CONVERSATION,
    SUPPORTED_IMAGE_MODELS,
    SUPPORTED_PROVIDERS,
    WORKERS_AI_MODEL_PREFIXES,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_ID): str,
        vol.Required(CONF_GATEWAY_ID, default=DEFAULT_GATEWAY_ID): str,
        vol.Required(CONF_CF_API_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""


class GatewayNotFound(Exception):
    """Error to indicate the gateway was not found."""


class ModelNotFound(Exception):
    """Error to indicate the model was not found."""


async def validate_gateway(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the gateway credentials.

    1. Verify the API token is valid via CF's token verify endpoint.
    2. Check the gateway endpoint responds (doesn't require management API perms).
    """
    api_token = data[CONF_CF_API_TOKEN]
    account_id = data[CONF_ACCOUNT_ID]
    gateway_id = data[CONF_GATEWAY_ID]

    client = get_async_client(hass)

    # Step 1: Verify the token itself is valid
    resp = await client.get(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10.0,
    )
    result = resp.json()
    if not result.get("success"):
        LOGGER.error("Token verification failed: %s", result.get("errors"))
        raise InvalidAuth

    # Step 2: Check the gateway endpoint is reachable
    resp = await client.get(
        f"https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat",
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10.0,
    )
    if resp.status_code == 404:
        LOGGER.error("Gateway not found: account=%s gateway=%s", account_id, gateway_id)
        raise GatewayNotFound
    # Any non-error response means the gateway exists (even 405 for wrong method is fine)


async def validate_model(hass: HomeAssistant, account_id: str, api_token: str, model: str) -> None:
    """Validate a Workers AI model exists.

    Queries the Cloudflare AI models API to verify the model name is valid.
    Only applicable for models that start with @cf/ or @hf/ (Workers AI models).
    """
    client = get_async_client(hass)
    resp = await client.get(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search",
        params={"search": model},
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10.0,
    )
    result = resp.json()
    if not result.get("success"):
        LOGGER.warning("Failed to validate model via CF API: %s", result.get("errors"))
        return

    models = result.get("result", [])
    for m in models:
        if m.get("name") == model:
            return

    raise ModelNotFound


class CloudflareAIGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cloudflare AI Gateway."""

    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_ACCOUNT_ID: user_input[CONF_ACCOUNT_ID],
                    CONF_GATEWAY_ID: user_input[CONF_GATEWAY_ID],
                }
            )
            try:
                await validate_gateway(self.hass, user_input)
            except (httpx.ConnectError, httpx.TimeoutException):
                LOGGER.error("Cannot connect to Cloudflare API")
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                LOGGER.error("Invalid Cloudflare API token")
                errors["base"] = "invalid_auth"
            except GatewayNotFound:
                LOGGER.error(
                    "Gateway '%s' not found for account '%s'",
                    user_input[CONF_GATEWAY_ID],
                    user_input[CONF_ACCOUNT_ID],
                )
                errors["base"] = "gateway_not_found"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="Cloudflare AI Gateway",
                    data=user_input,
                    subentries=[
                        {
                            "subentry_type": SUBENTRY_TYPE_CONVERSATION,
                            "title": "GLM 4.7 Flash",
                            "data": {
                                CONF_RECOMMENDED: True,
                                CONF_PROVIDER: DEFAULT_PROVIDER,
                                CONF_CHAT_MODEL: DEFAULT_CONVERSATION_MODEL,
                                CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
                            },
                            "unique_id": None,
                        },
                        {
                            "subentry_type": SUBENTRY_TYPE_AI_TASK_DATA,
                            "title": "Kimi K2.5",
                            "data": {
                                CONF_RECOMMENDED: True,
                                CONF_PROVIDER: DEFAULT_PROVIDER,
                                CONF_CHAT_MODEL: DEFAULT_AI_TASK_DATA_MODEL,
                            },
                            "unique_id": None,
                        },
                        {
                            "subentry_type": SUBENTRY_TYPE_AI_TASK_IMAGE,
                            "title": "FLUX.1 Schnell",
                            "data": {
                                CONF_IMAGE_MODEL: DEFAULT_IMAGE_MODEL,
                                CONF_IMAGE_WIDTH: DEFAULT_IMAGE_WIDTH,
                                CONF_IMAGE_HEIGHT: DEFAULT_IMAGE_HEIGHT,
                                CONF_IMAGE_STEPS: DEFAULT_IMAGE_STEPS,
                            },
                            "unique_id": None,
                        },
                    ],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauth when the API token becomes invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            data = {**reauth_entry.data, CONF_CF_API_TOKEN: user_input[CONF_CF_API_TOKEN]}
            try:
                await validate_gateway(self.hass, data)
            except (httpx.ConnectError, httpx.TimeoutException):
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except GatewayNotFound:
                errors["base"] = "gateway_not_found"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CF_API_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            SUBENTRY_TYPE_CONVERSATION: CloudflareChatSubentryFlowHandler,
            SUBENTRY_TYPE_AI_TASK_DATA: CloudflareChatSubentryFlowHandler,
            SUBENTRY_TYPE_AI_TASK_IMAGE: CloudflareImageSubentryFlowHandler,
        }


class CloudflareBaseSubentryFlowHandler(ConfigSubentryFlow):
    """Base flow handler with shared logic for all subentry types."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == SOURCE_USER

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Reconfigure an existing subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_user()

    async def _validate_workers_ai_model(self, model: str) -> None:
        """Validate a Workers AI model if applicable."""
        if not model.startswith(WORKERS_AI_MODEL_PREFIXES):
            return
        entry_data = self._get_entry().data
        await validate_model(
            self.hass,
            entry_data[CONF_ACCOUNT_ID],
            entry_data[CONF_CF_API_TOKEN],
            model,
        )


class CloudflareChatSubentryFlowHandler(CloudflareBaseSubentryFlowHandler):
    """Flow for adding/editing a conversation or AI task data subentry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Manage chat model options."""
        if user_input is None and not hasattr(self, "options"):
            self.options = {}
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        errors: dict[str, str] = {}
        options = self.options
        is_conversation = self._subentry_type == SUBENTRY_TYPE_CONVERSATION
        default_model = DEFAULT_CONVERSATION_MODEL if is_conversation else DEFAULT_AI_TASK_DATA_MODEL

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[vol.Required(CONF_NAME)] = str

        step_schema[
            vol.Optional(
                CONF_PROVIDER,
                default=options.get(CONF_PROVIDER, DEFAULT_PROVIDER),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=SUPPORTED_PROVIDERS,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        step_schema[
            vol.Optional(
                CONF_CHAT_MODEL,
                default=options.get(CONF_CHAT_MODEL, default_model),
            )
        ] = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        if is_conversation:
            apis = llm.async_get_apis(self.hass)
            hass_apis: list[SelectOptionDict] = [SelectOptionDict(label=api.name, value=api.id) for api in apis]
            if suggested_llm_apis := options.get(CONF_LLM_HASS_API):
                if isinstance(suggested_llm_apis, str):
                    suggested_llm_apis = [suggested_llm_apis]
                valid_apis = {api.id for api in apis}
                options[CONF_LLM_HASS_API] = [api for api in suggested_llm_apis if api in valid_apis]

            step_schema.update(
                {
                    vol.Optional(
                        CONF_PROMPT,
                        description={"suggested_value": options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT)},
                    ): TemplateSelector(),
                    vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                        SelectSelectorConfig(options=hass_apis, multiple=True)
                    ),
                }
            )

        step_schema[vol.Required(CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, False))] = bool

        if user_input is not None:
            if is_conversation and not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            # Validate Workers AI models against the CF API
            model = user_input.get(CONF_CHAT_MODEL, "")
            try:
                await self._validate_workers_ai_model(model)
            except ModelNotFound:
                errors[CONF_CHAT_MODEL] = "model_not_found"
            except (httpx.ConnectError, httpx.TimeoutException):
                LOGGER.warning("Could not validate model (network error), proceeding anyway")

            if not errors:
                if user_input[CONF_RECOMMENDED]:
                    if self._is_new:
                        return self.async_create_entry(
                            title=user_input.pop(CONF_NAME),
                            data=user_input,
                        )
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        data=user_input,
                    )

                options.update(user_input)
                if is_conversation and CONF_LLM_HASS_API in options and CONF_LLM_HASS_API not in user_input:
                    options.pop(CONF_LLM_HASS_API)
                return await self.async_step_advanced()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(step_schema), options),
            errors=errors,
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Manage advanced options."""
        options = self.options

        step_schema: VolDictType = {
            vol.Optional(
                CONF_MAX_TOKENS,
                default=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            ): int,
            vol.Optional(
                CONF_TOP_P,
                default=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            vol.Optional(
                CONF_TEMPERATURE,
                default=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
            vol.Optional(
                CONF_CACHE_TTL,
                description={"suggested_value": options.get(CONF_CACHE_TTL)},
            ): vol.All(int, vol.Range(min=0)),
        }

        if user_input is not None:
            if not user_input.get(CONF_CACHE_TTL):
                user_input.pop(CONF_CACHE_TTL, None)

            options.update(user_input)

            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(step_schema), options),
        )


class CloudflareImageSubentryFlowHandler(CloudflareBaseSubentryFlowHandler):
    """Flow for adding/editing an AI task image subentry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Manage image model options."""
        if user_input is None and not hasattr(self, "options"):
            self.options = {}
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        errors: dict[str, str] = {}
        options = self.options

        image_model_options = [SelectOptionDict(label=model, value=model) for model in SUPPORTED_IMAGE_MODELS]

        step_schema: VolDictType = {}

        if self._is_new:
            step_schema[vol.Required(CONF_NAME)] = str

        step_schema.update(
            {
                vol.Optional(
                    CONF_IMAGE_MODEL,
                    default=options.get(CONF_IMAGE_MODEL, DEFAULT_IMAGE_MODEL),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=image_model_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Optional(
                    CONF_IMAGE_WIDTH,
                    default=options.get(CONF_IMAGE_WIDTH, DEFAULT_IMAGE_WIDTH),
                ): NumberSelector(NumberSelectorConfig(min=256, max=2048, step=64)),
                vol.Optional(
                    CONF_IMAGE_HEIGHT,
                    default=options.get(CONF_IMAGE_HEIGHT, DEFAULT_IMAGE_HEIGHT),
                ): NumberSelector(NumberSelectorConfig(min=256, max=2048, step=64)),
                vol.Optional(
                    CONF_IMAGE_STEPS,
                    default=options.get(CONF_IMAGE_STEPS, DEFAULT_IMAGE_STEPS),
                ): NumberSelector(NumberSelectorConfig(min=1, max=20, step=1)),
            }
        )

        if user_input is not None:
            # Validate Workers AI image models against the CF API
            model = user_input.get(CONF_IMAGE_MODEL, "")
            try:
                await self._validate_workers_ai_model(model)
            except ModelNotFound:
                errors[CONF_IMAGE_MODEL] = "model_not_found"
            except (httpx.ConnectError, httpx.TimeoutException):
                LOGGER.warning("Could not validate model (network error), proceeding anyway")

            if not errors:
                if self._is_new:
                    return self.async_create_entry(
                        title=user_input.pop(CONF_NAME),
                        data=user_input,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(step_schema), options),
            errors=errors,
        )
