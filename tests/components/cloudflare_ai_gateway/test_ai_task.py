"""Tests for the Cloudflare AI Gateway AI Task entities."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.cloudflare_ai_gateway.const import (
    CONF_ACCOUNT_ID,
    CONF_CF_API_TOKEN,
    CONF_GATEWAY_ID,
    CONF_IMAGE_HEIGHT,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_STEPS,
    CONF_IMAGE_WIDTH,
    DEFAULT_IMAGE_MODEL,
    DOMAIN,
    SUBENTRY_TYPE_AI_TASK_IMAGE,
)
from homeassistant.components import ai_task
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def test_data_task_entity_is_registered(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
) -> None:
    """Test AI task data entity is set up from ai_task_data subentry."""
    ai_task_ids = [eid for eid in hass.states.async_entity_ids("ai_task") if eid != "ai_task.home_assistant"]
    assert len(ai_task_ids) == 1

    # Should not create a conversation entity
    conversation_ids = [
        eid for eid in hass.states.async_entity_ids("conversation") if eid != "conversation.home_assistant"
    ]
    assert len(conversation_ids) == 0


async def test_generate_data_plain_text(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test generate_data returns plain text."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    result = await ai_task.async_generate_data(
        hass,
        task_name="test_task",
        entity_id=entity_id,
        instructions="Say hello",
    )

    assert result.data == "Hello!"


async def test_generate_data_structured(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test generate_data with structured output parses JSON."""
    # Make the mock return JSON
    mock_create_stream.return_value = mock_create_stream.AsyncStreamHelper(
        [
            mock_create_stream.make_text_chunk('{"name": "test", "value": 42}', role="assistant"),
            mock_create_stream.make_text_chunk(None, finish_reason="stop"),
            mock_create_stream.make_usage_chunk(),
        ]
    )

    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    structure = vol.Schema(
        {
            vol.Required("name"): str,
            vol.Required("value"): int,
        }
    )

    result = await ai_task.async_generate_data(
        hass,
        task_name="test_structured",
        entity_id=entity_id,
        instructions="Generate data",
        structure=structure,
    )

    assert result.data == {"name": "test", "value": 42}

    # Verify response_format was passed to the API with strict mode
    call_kwargs = mock_create_stream.last_call_kwargs
    response_format = call_kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "tools" not in call_kwargs


async def test_generate_data_structured_invalid_json(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test generate_data with structured output raises on invalid JSON."""
    mock_create_stream.return_value = mock_create_stream.AsyncStreamHelper(
        [
            mock_create_stream.make_text_chunk("not valid json", role="assistant"),
            mock_create_stream.make_text_chunk(None, finish_reason="stop"),
            mock_create_stream.make_usage_chunk(),
        ]
    )

    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    structure = vol.Schema({vol.Required("name"): str})

    with pytest.raises(HomeAssistantError):
        await ai_task.async_generate_data(
            hass,
            task_name="test_bad_json",
            entity_id=entity_id,
            instructions="Generate data",
            structure=structure,
        )


async def test_image_task_entity_is_registered(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test AI task image entity is set up from image model subentry."""
    state = hass.states.async_entity_ids("ai_task")
    assert len(state) >= 1


async def test_generate_image(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test generate_image returns image data."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    fake_b64 = base64.b64encode(fake_image).decode()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": {"image": fake_b64}}
    mock_response.raise_for_status = MagicMock()

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = mock_response

        result = await ai_task.async_generate_image(
            hass,
            task_name="test_image",
            entity_id=entity_id,
            instructions="A cat",
        )

    assert result["mime_type"] == "image/png"
    assert result["width"] == 1024
    assert result["height"] == 1024

    # Verify the API was called with correct params
    call_args = mock_http.post.call_args
    assert "workers-ai" in call_args[0][0]
    assert call_args[1]["json"]["prompt"] == "A cat"


async def test_generate_image_sends_integer_dimensions(
    hass: HomeAssistant,
) -> None:
    """Test generate_image sends integer dimensions even if stored as floats."""
    # Create entry with float values (as NumberSelector would store)
    entry = MockConfigEntry(
        title="Cloudflare AI Gateway",
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: "test-account-id",
            CONF_GATEWAY_ID: "test-gateway",
            CONF_CF_API_TOKEN: "test-cf-token",
        },
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_IMAGE_MODEL: DEFAULT_IMAGE_MODEL,
                    CONF_IMAGE_WIDTH: 512.0,
                    CONF_IMAGE_HEIGHT: 768.0,
                    CONF_IMAGE_STEPS: 8.0,
                },
                subentry_type=SUBENTRY_TYPE_AI_TASK_IMAGE,
                title="Float Image Model",
                unique_id=None,
            ),
        ],
    )
    entry.add_to_hass(hass)

    # Init with mocked CF API
    cf_response = MagicMock()
    cf_response.status_code = 200
    cf_response.json.return_value = {"success": True, "result": {"status": "active"}}

    with (
        patch(
            "custom_components.cloudflare_ai_gateway.get_async_client",
        ) as mock_get_client,
        patch(
            "custom_components.cloudflare_ai_gateway.validate_model",
            new_callable=AsyncMock,
        ),
    ):
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = cf_response
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    fake_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": {"image": fake_b64}}
    mock_response.raise_for_status = MagicMock()

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = mock_response

        await ai_task.async_generate_image(
            hass,
            task_name="test_int_dims",
            entity_id=entity_id,
            instructions="A cat",
        )

    json_body = mock_http.post.call_args[1]["json"]
    assert isinstance(json_body["width"], int)
    assert isinstance(json_body["height"], int)
    assert isinstance(json_body["num_steps"], int)
    assert json_body["width"] == 512
    assert json_body["height"] == 768
    assert json_body["num_steps"] == 8


async def test_generate_image_connection_error(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test generate_image handles connection errors."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.side_effect = httpx.ConnectError("connection failed")

        with pytest.raises(HomeAssistantError, match="Cannot reach"):
            await ai_task.async_generate_image(
                hass,
                task_name="test_error",
                entity_id=entity_id,
                instructions="A cat",
            )


def _mock_http_status_error(status_code):
    """Create a mock httpx.HTTPStatusError."""
    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = status_code
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


async def test_generate_image_auth_error_triggers_reauth(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test that 401 errors on image generation trigger reauth."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _mock_http_status_error(401)

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = mock_response

        with pytest.raises(HomeAssistantError, match="Authentication failed"):
            await ai_task.async_generate_image(
                hass,
                task_name="test_auth",
                entity_id=entity_id,
                instructions="A cat",
            )

    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_generate_image_not_found_error(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test that 404 errors give a clear model-not-found message."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _mock_http_status_error(404)

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = mock_response

        with pytest.raises(HomeAssistantError, match="not found.*Check the model name"):
            await ai_task.async_generate_image(
                hass,
                task_name="test_404",
                entity_id=entity_id,
                instructions="A cat",
            )


async def test_generate_image_permission_denied_error(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test that 403 errors mention API token permissions."""
    entity_ids = hass.states.async_entity_ids("ai_task")
    entity_id = next(eid for eid in entity_ids if eid != "ai_task.home_assistant")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = _mock_http_status_error(403)

    with patch(
        "custom_components.cloudflare_ai_gateway.ai_task.get_async_client",
    ) as mock_get_client:
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.post.return_value = mock_response

        with pytest.raises(HomeAssistantError, match="Permission denied"):
            await ai_task.async_generate_image(
                hass,
                task_name="test_403",
                entity_id=entity_id,
                instructions="A cat",
            )
