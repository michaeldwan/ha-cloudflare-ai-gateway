"""Tests for Cloudflare AI Gateway usage monitoring sensors."""

from unittest.mock import AsyncMock, MagicMock, patch

import openai
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cloudflare_ai_gateway.const import ModelStats
from homeassistant.components import conversation
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, intent


async def test_sensor_entities_created_for_conversation_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that sensor entities are created for a conversation subentry."""
    sensor_ids = hass.states.async_entity_ids("sensor")
    assert len(sensor_ids) == 5


async def test_sensor_entities_created_for_ai_task_subentry(
    hass: HomeAssistant,
    mock_config_entry_with_ai_task_data: MockConfigEntry,
    mock_init_component_with_ai_task_data: None,
) -> None:
    """Test that sensor entities are created for an AI task data subentry."""
    sensor_ids = hass.states.async_entity_ids("sensor")
    assert len(sensor_ids) == 5


async def test_image_subentry_gets_request_and_error_sensors(
    hass: HomeAssistant,
    mock_config_entry_with_image_model: MockConfigEntry,
    mock_init_component_with_image_model: None,
) -> None:
    """Test that image subentries get only requests and errors sensors."""
    sensor_ids = hass.states.async_entity_ids("sensor")
    assert len(sensor_ids) == 2


async def test_sensors_initial_value_is_zero(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that sensors start at 0."""
    for sensor_id in hass.states.async_entity_ids("sensor"):
        state = hass.states.get(sensor_id)
        assert state is not None
        assert state.state == "0"


async def test_sensors_have_correct_state_class(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that all sensors use TOTAL state class with daily reset."""
    for sensor_id in hass.states.async_entity_ids("sensor"):
        state = hass.states.get(sensor_id)
        assert state is not None
        assert state.attributes.get("state_class") == "total"
        assert state.attributes.get("last_reset") is not None


async def test_sensors_are_diagnostic(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that all sensors have diagnostic entity category."""
    registry = er.async_get(hass)
    for sensor_id in hass.states.async_entity_ids("sensor"):
        entry = registry.async_get(sensor_id)
        assert entry is not None
        assert entry.entity_category == EntityCategory.DIAGNOSTIC


async def test_sensors_share_device_with_conversation_entity(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that sensor entities share a device with the conversation entity."""
    registry = er.async_get(hass)

    conv_ids = hass.states.async_entity_ids("conversation")
    conv_id = next(eid for eid in conv_ids if eid != "conversation.home_assistant")
    conv_entry = registry.async_get(conv_id)
    assert conv_entry is not None

    for sensor_id in hass.states.async_entity_ids("sensor"):
        sensor_entry = registry.async_get(sensor_id)
        assert sensor_entry is not None
        assert sensor_entry.device_id == conv_entry.device_id


async def test_sensors_update_after_conversation(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test that sensors increment after a conversation request."""
    entity_ids = hass.states.async_entity_ids("conversation")
    agent_id = next(eid for eid in entity_ids if eid != "conversation.home_assistant")

    result = await conversation.async_converse(
        hass,
        "Hello",
        conversation_id=None,
        context=None,
        agent_id=agent_id,
    )
    assert result.response.response_type == intent.IntentResponseType.ACTION_DONE
    await hass.async_block_till_done()

    # Check stats were accumulated in runtime data
    subentry_id = next(iter(mock_config_entry_with_subentries.subentries))
    stats = mock_config_entry_with_subentries.runtime_data.model_stats[subentry_id]
    assert stats.total_requests == 1
    assert stats.input_tokens == 10
    assert stats.output_tokens == 5

    # Verify sensor states actually updated in HA
    registry = er.async_get(hass)
    for sensor_id in hass.states.async_entity_ids("sensor"):
        entry = registry.async_get(sensor_id)
        state = hass.states.get(sensor_id)
        if entry and entry.translation_key == "requests":
            assert state.state == "1"
        elif entry and entry.translation_key == "input_tokens":
            assert state.state == "10"
        elif entry and entry.translation_key == "output_tokens":
            assert state.state == "5"


async def test_sensors_count_errors(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test that error sensors increment on API errors."""
    mock_response = AsyncMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {"error": {"message": "rate limited"}}
    mock_response.headers = {}
    mock_create_stream.side_effect = openai.RateLimitError(
        message="rate limited",
        response=mock_response,
        body={"error": {"message": "rate limited"}},
    )

    entity_ids = hass.states.async_entity_ids("conversation")
    agent_id = next(eid for eid in entity_ids if eid != "conversation.home_assistant")

    await conversation.async_converse(
        hass,
        "Hello",
        conversation_id=None,
        context=None,
        agent_id=agent_id,
    )
    await hass.async_block_till_done()

    subentry_id = next(iter(mock_config_entry_with_subentries.subentries))
    stats = mock_config_entry_with_subentries.runtime_data.model_stats[subentry_id]
    assert stats.total_errors == 1
    assert stats.total_requests == 0


async def test_sensors_track_cache_hits(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
    mock_create_stream: AsyncMock,
) -> None:
    """Test that cache hit/miss sensors track from response headers."""
    mock_create_stream.response_headers = {"cf-aig-cache-status": "HIT"}

    entity_ids = hass.states.async_entity_ids("conversation")
    agent_id = next(eid for eid in entity_ids if eid != "conversation.home_assistant")

    await conversation.async_converse(
        hass,
        "Hello",
        conversation_id=None,
        context=None,
        agent_id=agent_id,
    )
    await hass.async_block_till_done()

    subentry_id = next(iter(mock_config_entry_with_subentries.subentries))
    stats = mock_config_entry_with_subentries.runtime_data.model_stats[subentry_id]
    assert stats.cache_hits == 1


async def test_sensors_reset_daily(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that model stats reset when the date changes."""
    stats = ModelStats(
        total_requests=5,
        total_errors=1,
        input_tokens=100,
        output_tokens=50,
        cache_hits=2,
        reset_date="2020-01-01",
    )

    # Same day — no reset
    stats.maybe_reset("2020-01-01")
    assert stats.total_requests == 5

    # New day — counters reset
    stats.maybe_reset("2020-01-02")
    assert stats.total_requests == 0
    assert stats.total_errors == 0
    assert stats.input_tokens == 0
    assert stats.output_tokens == 0
    assert stats.cache_hits == 0
    assert stats.reset_date == "2020-01-02"


# --- Gateway cost sensor ---


async def test_cost_sensor_not_created_without_analytics(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
    mock_init_component_with_subentries: None,
) -> None:
    """Test that no cost sensor is created when analytics is not available."""
    sensor_ids = hass.states.async_entity_ids("sensor")
    cost_sensors = [s for s in sensor_ids if "cost" in s]
    assert len(cost_sensors) == 0


async def test_cost_sensor_created_with_analytics(
    hass: HomeAssistant,
    mock_config_entry_with_subentries: MockConfigEntry,
) -> None:
    """Test that cost sensor is created when analytics coordinator is available."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "result": {"status": "active"}}

    graphql_response = MagicMock()
    graphql_response.json.return_value = {
        "data": {
            "viewer": {
                "accounts": [
                    {
                        "today": [
                            {"count": 5, "sum": {"cost": 0.0042}},
                        ]
                    }
                ]
            }
        },
        "errors": None,
    }

    with (
        patch(
            "custom_components.cloudflare_ai_gateway.get_async_client",
        ) as mock_get_client,
        patch(
            "custom_components.cloudflare_ai_gateway.validate_model",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.cloudflare_ai_gateway.coordinator.get_async_client",
        ) as mock_gql_client,
    ):
        mock_http = AsyncMock()
        mock_get_client.return_value = mock_http
        mock_http.get.return_value = mock_response

        mock_gql_http = AsyncMock()
        mock_gql_client.return_value = mock_gql_http
        mock_gql_http.post.return_value = graphql_response

        await hass.config_entries.async_setup(mock_config_entry_with_subentries.entry_id)
        await hass.async_block_till_done()

    # Should have the cost sensor
    sensor_ids = hass.states.async_entity_ids("sensor")
    cost_sensors = [s for s in sensor_ids if "cost" in s]
    assert len(cost_sensors) == 1

    state = hass.states.get(cost_sensors[0])
    assert state is not None
    assert float(state.state) == 0.0042
    assert state.attributes.get("device_class") == "monetary"
    assert state.attributes.get("state_class") == "total"
    assert state.attributes.get("unit_of_measurement") == "USD"

    # Verify it's on a gateway device, not a model device
    registry = er.async_get(hass)
    entry = registry.async_get(cost_sensors[0])
    assert entry is not None
    assert entry.entity_category == EntityCategory.DIAGNOSTIC
