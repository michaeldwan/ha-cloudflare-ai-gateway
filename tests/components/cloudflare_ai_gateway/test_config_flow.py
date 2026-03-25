"""Tests for the Cloudflare AI Gateway config flow."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cloudflare_ai_gateway.config_flow import GatewayNotFound, InvalidAuth, ModelNotFound
from custom_components.cloudflare_ai_gateway.const import (
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
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_STEPS,
    DEFAULT_IMAGE_WIDTH,
    DEFAULT_PROVIDER,
    DOMAIN,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    SUBENTRY_TYPE_AI_TASK_DATA,
    SUBENTRY_TYPE_AI_TASK_IMAGE,
    SUBENTRY_TYPE_CONVERSATION,
)
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

GATEWAY_DATA = {
    CONF_ACCOUNT_ID: "test-account",
    CONF_GATEWAY_ID: "default",
    CONF_CF_API_TOKEN: "test-token",
}


# --- Parent config entry flow ---


async def test_form_creates_entry_with_default_subentries(hass: HomeAssistant) -> None:
    """Test we can create an entry with default conversation and AI task subentries."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_gateway",
        new_callable=AsyncMock,
    ) as mock_validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            GATEWAY_DATA,
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cloudflare AI Gateway"
    assert result["data"] == GATEWAY_DATA
    mock_validate.assert_called_once()

    # Verify default subentries were created
    subentries = result.get("subentries", ())
    assert len(subentries) == 3

    types = {s["subentry_type"] for s in subentries}
    assert types == {SUBENTRY_TYPE_CONVERSATION, SUBENTRY_TYPE_AI_TASK_DATA, SUBENTRY_TYPE_AI_TASK_IMAGE}

    for s in subentries:
        if s["subentry_type"] == SUBENTRY_TYPE_CONVERSATION:
            assert s["title"] == "GLM 4.7 Flash"
            assert s["data"][CONF_PROVIDER] == DEFAULT_PROVIDER
            assert s["data"][CONF_CHAT_MODEL] == DEFAULT_CONVERSATION_MODEL
            assert s["data"][CONF_RECOMMENDED] is True
            assert s["data"][CONF_LLM_HASS_API] == ["assist"]
        elif s["subentry_type"] == SUBENTRY_TYPE_AI_TASK_DATA:
            assert s["title"] == "Kimi K2.5"
            assert s["data"][CONF_PROVIDER] == DEFAULT_PROVIDER
            assert s["data"][CONF_CHAT_MODEL] == DEFAULT_AI_TASK_DATA_MODEL
            assert s["data"][CONF_RECOMMENDED] is True
        elif s["subentry_type"] == SUBENTRY_TYPE_AI_TASK_IMAGE:
            assert s["title"] == "FLUX.1 Schnell"
            assert s["data"][CONF_IMAGE_MODEL] == DEFAULT_IMAGE_MODEL
            assert s["data"][CONF_IMAGE_WIDTH] == DEFAULT_IMAGE_WIDTH
            assert s["data"][CONF_IMAGE_HEIGHT] == DEFAULT_IMAGE_HEIGHT
            assert s["data"][CONF_IMAGE_STEPS] == DEFAULT_IMAGE_STEPS
        else:
            pytest.fail(f"Unexpected subentry type: {s['subentry_type']}")


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (InvalidAuth, "invalid_auth"),
        (GatewayNotFound, "gateway_not_found"),
        (httpx.ConnectError("connection failed"), "cannot_connect"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_form_errors(hass: HomeAssistant, side_effect: Exception, error: str) -> None:
    """Test we handle various errors."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_gateway",
        new_callable=AsyncMock,
        side_effect=side_effect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            GATEWAY_DATA,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_duplicate_entry(hass: HomeAssistant) -> None:
    """Test we abort if already configured with same account+gateway."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=GATEWAY_DATA,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        GATEWAY_DATA,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- Conversation subentry flow ---


async def test_creating_conversation_recommended(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating a conversation subentry with recommended options."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "My Model",
            CONF_PROVIDER: "anthropic",
            CONF_CHAT_MODEL: "claude-sonnet-4-20250514",
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Model"
    assert result["data"] == {
        CONF_PROVIDER: "anthropic",
        CONF_CHAT_MODEL: "claude-sonnet-4-20250514",
        CONF_RECOMMENDED: True,
    }


async def test_creating_conversation_advanced(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating a conversation subentry with advanced options."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Custom Model",
            CONF_PROVIDER: "openai",
            CONF_CHAT_MODEL: "gpt-4o",
            CONF_RECOMMENDED: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MAX_TOKENS: 4096,
            CONF_TOP_P: 0.9,
            CONF_TEMPERATURE: 0.7,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Custom Model"
    assert result["data"] == {
        CONF_PROVIDER: "openai",
        CONF_CHAT_MODEL: "gpt-4o",
        CONF_RECOMMENDED: False,
        CONF_MAX_TOKENS: 4096,
        CONF_TOP_P: 0.9,
        CONF_TEMPERATURE: 0.7,
    }


async def test_creating_conversation_advanced_with_cache_ttl(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating a conversation subentry with cache TTL set."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Cached Model",
            CONF_PROVIDER: "openai",
            CONF_CHAT_MODEL: "gpt-4o-mini",
            CONF_RECOMMENDED: False,
        },
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MAX_TOKENS: RECOMMENDED_MAX_TOKENS,
            CONF_TOP_P: RECOMMENDED_TOP_P,
            CONF_TEMPERATURE: RECOMMENDED_TEMPERATURE,
            CONF_CACHE_TTL: 300,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CACHE_TTL] == 300


async def test_creating_conversation_workers_ai_invalid_model(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating a conversation with an invalid Workers AI model shows error."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
        side_effect=ModelNotFound,
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "name": "Bad Model",
                CONF_PROVIDER: "workers-ai",
                CONF_CHAT_MODEL: "@cf/moonshot/kimi-k2.5",
                CONF_RECOMMENDED: True,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_CHAT_MODEL: "model_not_found"}


async def test_creating_conversation_workers_ai_valid_model(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating a conversation with a valid Workers AI model succeeds."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "name": "Workers AI Model",
                CONF_PROVIDER: "workers-ai",
                CONF_CHAT_MODEL: "@cf/moonshotai/kimi-k2.5",
                CONF_RECOMMENDED: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CHAT_MODEL] == "@cf/moonshotai/kimi-k2.5"


async def test_creating_conversation_non_workers_ai_skips_validation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that non-Workers AI models skip model validation."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
    ) as mock_validate:
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "name": "OpenAI Model",
                CONF_PROVIDER: "openai",
                CONF_CHAT_MODEL: "gpt-4o",
                CONF_RECOMMENDED: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_validate.assert_not_called()


async def test_creating_conversation_validation_network_error_proceeds(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that network errors during validation don't block model creation."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timeout"),
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "name": "Workers AI Model",
                CONF_PROVIDER: "workers-ai",
                CONF_CHAT_MODEL: "@cf/moonshotai/kimi-k2.5",
                CONF_RECOMMENDED: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_creating_subentry_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test creating a subentry aborts when the config entry is not loaded."""
    assert mock_config_entry.state is not ConfigEntryState.LOADED

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


async def test_reconfigure_conversation_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test reconfiguring an existing conversation subentry."""
    subentry = next(iter(mock_config_entry_with_subentries.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry_with_subentries.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_PROVIDER: "anthropic",
            CONF_CHAT_MODEL: "claude-sonnet-4-20250514",
            CONF_RECOMMENDED: True,
        },
    )
    # Reconfigure uses async_update_and_abort which results in ABORT with reason reconfigure_successful
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    # Verify the subentry data was updated
    updated_subentry = mock_config_entry_with_subentries.subentries[subentry.subentry_id]
    assert updated_subentry.data[CONF_PROVIDER] == "anthropic"
    assert updated_subentry.data[CONF_CHAT_MODEL] == "claude-sonnet-4-20250514"


# --- AI task data subentry flow ---


async def test_creating_ai_task_data_recommended(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating an AI task data subentry with recommended options."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_DATA),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # Verify prompt and LLM API fields are NOT in the schema
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert CONF_PROMPT not in schema_keys
    assert CONF_LLM_HASS_API not in schema_keys

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "My Data Task",
            CONF_PROVIDER: "openai",
            CONF_CHAT_MODEL: "gpt-4o-mini",
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Data Task"
    assert result["data"] == {
        CONF_PROVIDER: "openai",
        CONF_CHAT_MODEL: "gpt-4o-mini",
        CONF_RECOMMENDED: True,
    }


async def test_creating_ai_task_data_advanced(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating an AI task data subentry with advanced options."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_DATA),
        context={"source": "user"},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Custom Data Task",
            CONF_PROVIDER: "openai",
            CONF_CHAT_MODEL: "gpt-4o",
            CONF_RECOMMENDED: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MAX_TOKENS: 8192,
            CONF_TOP_P: 0.95,
            CONF_TEMPERATURE: 0.5,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Custom Data Task"
    assert result["data"] == {
        CONF_PROVIDER: "openai",
        CONF_CHAT_MODEL: "gpt-4o",
        CONF_RECOMMENDED: False,
        CONF_MAX_TOKENS: 8192,
        CONF_TOP_P: 0.95,
        CONF_TEMPERATURE: 0.5,
    }


async def test_creating_ai_task_data_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test creating an AI task data subentry aborts when entry is not loaded."""
    assert mock_config_entry.state is not ConfigEntryState.LOADED

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_DATA),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


async def test_reconfigure_ai_task_data_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
) -> None:
    """Test reconfiguring an existing AI task data subentry."""
    subentry = next(iter(mock_config_entry_with_ai_task_data.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry_with_ai_task_data.entry_id, SUBENTRY_TYPE_AI_TASK_DATA),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_PROVIDER: "anthropic",
            CONF_CHAT_MODEL: "claude-sonnet-4-20250514",
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    updated_subentry = mock_config_entry_with_ai_task_data.subentries[subentry.subentry_id]
    assert updated_subentry.data[CONF_PROVIDER] == "anthropic"


async def test_conversation_form_includes_prompt_and_llm_api(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that conversation form includes prompt and LLM API fields."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM

    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert CONF_PROMPT in schema_keys
    assert CONF_LLM_HASS_API in schema_keys


async def test_conversation_form_defaults(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that conversation form defaults to workers-ai provider and GLM flash model."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_CONVERSATION),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM

    schema = result["data_schema"].schema
    defaults = {str(k): k.default() if callable(k.default) else k.default for k in schema if hasattr(k, "default")}
    assert defaults[CONF_PROVIDER] == DEFAULT_PROVIDER
    assert defaults[CONF_CHAT_MODEL] == DEFAULT_CONVERSATION_MODEL


async def test_ai_task_data_form_defaults(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test that AI task data form defaults to workers-ai provider and Kimi model."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_DATA),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM

    schema = result["data_schema"].schema
    defaults = {str(k): k.default() if callable(k.default) else k.default for k in schema if hasattr(k, "default")}
    assert defaults[CONF_PROVIDER] == DEFAULT_PROVIDER
    assert defaults[CONF_CHAT_MODEL] == DEFAULT_AI_TASK_DATA_MODEL


async def test_creating_image_subentry_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test creating an image subentry aborts when entry is not loaded."""
    assert mock_config_entry.state is not ConfigEntryState.LOADED

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_IMAGE),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


# --- Reauth flow ---


async def test_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test reauthentication flow updates the API token."""
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_gateway",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CF_API_TOKEN: "new-token"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_CF_API_TOKEN] == "new-token"


async def test_reauth_invalid_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test reauthentication flow shows error for invalid token."""
    result = await mock_config_entry.start_reauth_flow(hass)

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_gateway",
        new_callable=AsyncMock,
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CF_API_TOKEN: "bad-token"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


# --- AI task image subentry flow ---


async def test_creating_image_model_subentry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_init_component: None,
) -> None:
    """Test creating an image model subentry."""
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_AI_TASK_IMAGE),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "name": "My Image Model",
                CONF_IMAGE_MODEL: DEFAULT_IMAGE_MODEL,
                CONF_IMAGE_WIDTH: DEFAULT_IMAGE_WIDTH,
                CONF_IMAGE_HEIGHT: DEFAULT_IMAGE_HEIGHT,
                CONF_IMAGE_STEPS: DEFAULT_IMAGE_STEPS,
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Image Model"
    assert result["data"] == {
        CONF_IMAGE_MODEL: DEFAULT_IMAGE_MODEL,
        CONF_IMAGE_WIDTH: DEFAULT_IMAGE_WIDTH,
        CONF_IMAGE_HEIGHT: DEFAULT_IMAGE_HEIGHT,
        CONF_IMAGE_STEPS: DEFAULT_IMAGE_STEPS,
    }


async def test_reconfigure_image_model_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test reconfiguring an existing image model subentry."""
    subentry = next(iter(mock_config_entry_with_image_model.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry_with_image_model.entry_id, SUBENTRY_TYPE_AI_TASK_IMAGE),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.cloudflare_ai_gateway.config_flow.validate_model",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_IMAGE_MODEL: "@cf/stabilityai/stable-diffusion-xl-base-1.0",
                CONF_IMAGE_WIDTH: 512,
                CONF_IMAGE_HEIGHT: 512,
                CONF_IMAGE_STEPS: 8,
            },
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    updated_subentry = mock_config_entry_with_image_model.subentries[subentry.subentry_id]
    assert updated_subentry.data[CONF_IMAGE_MODEL] == "@cf/stabilityai/stable-diffusion-xl-base-1.0"
