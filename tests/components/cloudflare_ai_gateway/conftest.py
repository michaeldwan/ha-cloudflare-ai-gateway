"""Fixtures for Cloudflare AI Gateway tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cloudflare_ai_gateway.const import (
    CONF_ACCOUNT_ID,
    CONF_CF_API_TOKEN,
    CONF_CHAT_MODEL,
    CONF_GATEWAY_ID,
    CONF_IMAGE_HEIGHT,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_STEPS,
    CONF_IMAGE_WIDTH,
    CONF_MODEL_TYPE,
    CONF_PROVIDER,
    CONF_RECOMMENDED,
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_STEPS,
    DEFAULT_IMAGE_WIDTH,
    DOMAIN,
    MODEL_TYPE_CHAT,
    MODEL_TYPE_IMAGE,
    SUBENTRY_TYPE_MODEL,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Mock a config entry with no subentries (gateway only)."""
    entry = MockConfigEntry(
        title="Cloudflare AI Gateway",
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: "test-account-id",
            CONF_GATEWAY_ID: "test-gateway",
            CONF_CF_API_TOKEN: "test-cf-token",
        },
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_with_subentries(hass: HomeAssistant) -> MockConfigEntry:
    """Mock a config entry with a chat model subentry."""
    entry = MockConfigEntry(
        title="Cloudflare AI Gateway",
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: "test-account-id",
            CONF_GATEWAY_ID: "test-gateway",
            CONF_CF_API_TOKEN: "test-cf-token",
        },
        version=1,
        minor_version=1,
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_MODEL_TYPE: MODEL_TYPE_CHAT,
                    CONF_RECOMMENDED: True,
                    CONF_PROVIDER: "openai",
                    CONF_CHAT_MODEL: "gpt-4o-mini",
                    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
                },
                subentry_type=SUBENTRY_TYPE_MODEL,
                title="Test Conversation",
                unique_id=None,
            ),
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_no_llm_api(hass: HomeAssistant) -> MockConfigEntry:
    """Mock a config entry with a chat model subentry but no LLM API configured."""
    entry = MockConfigEntry(
        title="Cloudflare AI Gateway",
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: "test-account-id",
            CONF_GATEWAY_ID: "test-gateway",
            CONF_CF_API_TOKEN: "test-cf-token",
        },
        version=1,
        minor_version=1,
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_MODEL_TYPE: MODEL_TYPE_CHAT,
                    CONF_RECOMMENDED: True,
                    CONF_PROVIDER: "openai",
                    CONF_CHAT_MODEL: "gpt-4o-mini",
                },
                subentry_type=SUBENTRY_TYPE_MODEL,
                title="Test No LLM",
                unique_id=None,
            ),
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def mock_init_component_no_llm_api(hass: HomeAssistant, mock_config_entry_no_llm_api: MockConfigEntry) -> None:
    """Initialize integration without LLM API configured."""
    await _mock_init(hass, mock_config_entry_no_llm_api)()


@pytest.fixture
def mock_config_entry_with_assist(
    hass: HomeAssistant, mock_config_entry_with_subentries: MockConfigEntry
) -> MockConfigEntry:
    """Mock a config entry with assist."""
    hass.config_entries.async_update_subentry(
        mock_config_entry_with_subentries,
        next(iter(mock_config_entry_with_subentries.subentries.values())),
        data={CONF_LLM_HASS_API: llm.LLM_API_ASSIST},
    )
    return mock_config_entry_with_subentries


@pytest.fixture
def mock_config_entry_with_image_model(hass: HomeAssistant) -> MockConfigEntry:
    """Mock a config entry with an image model subentry."""
    entry = MockConfigEntry(
        title="Cloudflare AI Gateway",
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_ID: "test-account-id",
            CONF_GATEWAY_ID: "test-gateway",
            CONF_CF_API_TOKEN: "test-cf-token",
        },
        version=1,
        minor_version=1,
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_MODEL_TYPE: MODEL_TYPE_IMAGE,
                    CONF_IMAGE_MODEL: DEFAULT_IMAGE_MODEL,
                    CONF_IMAGE_WIDTH: DEFAULT_IMAGE_WIDTH,
                    CONF_IMAGE_HEIGHT: DEFAULT_IMAGE_HEIGHT,
                    CONF_IMAGE_STEPS: DEFAULT_IMAGE_STEPS,
                },
                subentry_type=SUBENTRY_TYPE_MODEL,
                title="Test Image Model",
                unique_id=None,
            ),
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def mock_init_component_with_image_model(
    hass: HomeAssistant, mock_config_entry_with_image_model: MockConfigEntry
) -> None:
    """Initialize integration with image model subentry."""
    await _mock_init(hass, mock_config_entry_with_image_model)()


def _mock_init(hass, entry):
    """Shared helper to init the integration with mocked CF API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True, "result": {"status": "active"}}

    async def _setup():
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
            mock_http.get.return_value = mock_response
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

    return _setup


@pytest.fixture
async def mock_init_component(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Initialize integration with gateway-only entry."""
    await _mock_init(hass, mock_config_entry)()


@pytest.fixture
async def mock_init_component_with_subentries(
    hass: HomeAssistant, mock_config_entry_with_subentries: MockConfigEntry
) -> None:
    """Initialize integration with subentries."""
    await _mock_init(hass, mock_config_entry_with_subentries)()


@pytest.fixture(autouse=True)
async def setup_ha(hass: HomeAssistant) -> None:
    """Set up Home Assistant."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
def mock_create_stream() -> Generator[AsyncMock]:
    """Mock streaming chat completion response."""

    class AsyncStreamHelper:
        """Helper to simulate async streaming."""

        def __init__(self, chunks: list) -> None:
            self.chunks = chunks

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.chunks:
                raise StopAsyncIteration
            return self.chunks.pop(0)

    def make_text_chunk(content: str, *, role: str | None = None, finish_reason: str | None = None):
        """Create a mock streaming chunk with text content."""
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock()
        chunk.choices[0].delta.role = role
        chunk.choices[0].delta.content = content
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = finish_reason
        chunk.usage = None
        return chunk

    def make_usage_chunk(prompt_tokens: int = 10, completion_tokens: int = 5):
        """Create a mock usage chunk."""
        chunk = MagicMock()
        chunk.choices = []
        chunk.usage = MagicMock()
        chunk.usage.prompt_tokens = prompt_tokens
        chunk.usage.completion_tokens = completion_tokens
        return chunk

    with patch(
        "custom_components.cloudflare_ai_gateway.entity.openai.AsyncOpenAI",
    ) as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        mock_create = AsyncMock()
        mock_client.chat.completions.create = mock_create

        # Default: simple text response
        mock_create.return_value = AsyncStreamHelper(
            [
                make_text_chunk("Hello!", role="assistant"),
                make_text_chunk(None, finish_reason="stop"),
                make_usage_chunk(),
            ]
        )

        # Attach helpers for custom responses
        mock_create.make_text_chunk = make_text_chunk
        mock_create.make_usage_chunk = make_usage_chunk
        mock_create.AsyncStreamHelper = AsyncStreamHelper

        yield mock_create
