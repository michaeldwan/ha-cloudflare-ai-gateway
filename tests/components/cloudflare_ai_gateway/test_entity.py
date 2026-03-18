"""Tests for Cloudflare AI Gateway entity base logic."""

from unittest.mock import MagicMock

import pytest

from custom_components.cloudflare_ai_gateway.entity import (
    _add_additional_properties_false,
    _convert_content_to_messages,
    _transform_stream,
)
from homeassistant.components import conversation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

# --- _convert_content_to_messages ---


def test_convert_system_message():
    """Test system message conversion."""
    content = [conversation.SystemContent(content="You are helpful.")]
    messages = _convert_content_to_messages(content)
    assert messages == [{"role": "system", "content": "You are helpful."}]


def test_convert_user_message():
    """Test user message conversion."""
    content = [conversation.UserContent(content="Hello")]
    messages = _convert_content_to_messages(content)
    assert messages == [{"role": "user", "content": "Hello"}]


def test_convert_assistant_message_with_text():
    """Test assistant message with text content."""
    content = [conversation.AssistantContent(agent_id="test", content="Hi there!")]
    messages = _convert_content_to_messages(content)
    assert messages == [{"role": "assistant", "content": "Hi there!"}]


def test_convert_assistant_message_with_tool_calls():
    """Test assistant message with tool calls."""
    content = [
        conversation.AssistantContent(
            agent_id="test",
            tool_calls=[
                llm.ToolInput(id="call_1", tool_name="get_weather", tool_args={"city": "London"}),
            ],
        )
    ]
    messages = _convert_content_to_messages(content)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert "content" not in messages[0]
    assert len(messages[0]["tool_calls"]) == 1
    tc = messages[0]["tool_calls"][0]
    assert tc["id"] == "call_1"
    assert tc["function"]["name"] == "get_weather"
    assert '"city"' in tc["function"]["arguments"]


def test_convert_tool_result():
    """Test tool result conversion."""
    content = [
        conversation.ToolResultContent(
            agent_id="test",
            tool_call_id="call_1",
            tool_name="get_weather",
            tool_result={"temperature": 20},
        )
    ]
    messages = _convert_content_to_messages(content)
    assert len(messages) == 1
    assert messages[0]["role"] == "tool"
    assert messages[0]["tool_call_id"] == "call_1"
    assert "20" in messages[0]["content"]


def test_convert_empty_content():
    """Test empty content handling."""
    messages = _convert_content_to_messages([])
    assert messages == []


def test_convert_mixed_conversation():
    """Test a full conversation with multiple message types."""
    content = [
        conversation.SystemContent(content="Be helpful"),
        conversation.UserContent(content="What's the weather?"),
        conversation.AssistantContent(
            agent_id="test",
            tool_calls=[llm.ToolInput(id="c1", tool_name="get_weather", tool_args={"city": "NYC"})],
        ),
        conversation.ToolResultContent(
            agent_id="test", tool_call_id="c1", tool_name="get_weather", tool_result="Sunny, 25C"
        ),
        conversation.AssistantContent(agent_id="test", content="It's sunny and 25C in NYC!"),
    ]
    messages = _convert_content_to_messages(content)
    assert len(messages) == 5
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert "tool_calls" in messages[2]
    assert messages[3]["role"] == "tool"
    assert messages[4]["role"] == "assistant"
    assert messages[4]["content"] == "It's sunny and 25C in NYC!"


# --- _transform_stream ---


def _make_chunk(
    *,
    content=None,
    role=None,
    finish_reason=None,
    tool_calls=None,
    usage=None,
    no_choices=False,
):
    """Create a mock streaming chunk."""
    chunk = MagicMock()
    if no_choices:
        chunk.choices = []
        chunk.usage = usage
        return chunk

    choice = MagicMock()
    choice.delta.role = role
    choice.delta.content = content
    choice.delta.tool_calls = tool_calls
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


def _make_tc_delta(index, *, tool_id=None, name=None, arguments=None):
    """Create a mock tool call delta."""
    tc = MagicMock()
    tc.index = index
    tc.id = tool_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


async def _collect_stream(chunks):
    """Run _transform_stream and collect all yielded deltas."""
    chat_log = MagicMock()

    async def _async_iter():
        for c in chunks:
            yield c

    stream = _async_iter()
    deltas = [delta async for delta in _transform_stream(chat_log, stream)]
    return deltas, chat_log


async def test_stream_basic_text():
    """Test basic text streaming."""
    chunks = [
        _make_chunk(role="assistant", content="Hello"),
        _make_chunk(content=" world"),
        _make_chunk(content="!", finish_reason="stop"),
    ]
    deltas, _ = await _collect_stream(chunks)

    assert deltas[0] == {"role": "assistant"}
    assert deltas[1] == {"content": "Hello"}
    assert deltas[2] == {"content": " world"}
    assert deltas[3] == {"content": "!"}


async def test_stream_usage_stats():
    """Test usage stats are traced."""
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    chunks = [
        _make_chunk(role="assistant", content="Hi"),
        _make_chunk(content=None, finish_reason="stop"),
        _make_chunk(no_choices=True, usage=usage),
    ]
    deltas, chat_log = await _collect_stream(chunks)

    chat_log.async_trace.assert_called_once()
    trace_data = chat_log.async_trace.call_args[0][0]
    assert trace_data["stats"]["input_tokens"] == 10
    assert trace_data["stats"]["output_tokens"] == 5


async def test_stream_tool_call():
    """Test tool call accumulation and yielding."""
    chunks = [
        _make_chunk(
            role="assistant",
            tool_calls=[_make_tc_delta(0, tool_id="call_1", name="get_temp", arguments='{"city":')],
        ),
        _make_chunk(tool_calls=[_make_tc_delta(0, arguments='"NYC"}')]),
        _make_chunk(finish_reason="tool_calls"),
    ]
    deltas, _ = await _collect_stream(chunks)

    assert deltas[0] == {"role": "assistant"}
    tool_delta = deltas[1]
    assert "tool_calls" in tool_delta
    tc = tool_delta["tool_calls"][0]
    assert tc.id == "call_1"
    assert tc.tool_name == "get_temp"
    assert tc.tool_args == {"city": "NYC"}


async def test_stream_multiple_tool_calls():
    """Test multiple tool calls in a single response."""
    chunks = [
        _make_chunk(
            role="assistant",
            tool_calls=[
                _make_tc_delta(0, tool_id="call_1", name="get_temp", arguments='{"city": "NYC"}'),
                _make_tc_delta(1, tool_id="call_2", name="get_time", arguments='{"tz": "EST"}'),
            ],
        ),
        _make_chunk(finish_reason="tool_calls"),
    ]
    deltas, _ = await _collect_stream(chunks)

    assert deltas[0] == {"role": "assistant"}
    tool_deltas = [d for d in deltas if "tool_calls" in d]
    assert len(tool_deltas) == 2
    assert tool_deltas[0]["tool_calls"][0].tool_name == "get_temp"
    assert tool_deltas[1]["tool_calls"][0].tool_name == "get_time"


async def test_stream_finish_reason_length():
    """Test that finish_reason=length raises HomeAssistantError."""
    chunks = [
        _make_chunk(role="assistant", content="partial"),
        _make_chunk(finish_reason="length"),
    ]
    with pytest.raises(HomeAssistantError, match="max output tokens"):
        await _collect_stream(chunks)


async def test_stream_usage_without_choices_skipped():
    """Test that a chunk with no choices and no usage is skipped."""
    chunks = [
        _make_chunk(role="assistant", content="Hi"),
        _make_chunk(no_choices=True, usage=None),
        _make_chunk(content="!", finish_reason="stop"),
    ]
    deltas, chat_log = await _collect_stream(chunks)

    chat_log.async_trace.assert_not_called()
    content_deltas = [d.get("content") for d in deltas if "content" in d]
    assert "Hi" in content_deltas
    assert "!" in content_deltas


# --- _add_additional_properties_false ---


def test_additional_properties_simple_object():
    """Test additionalProperties added to simple object."""
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    _add_additional_properties_false(schema)
    assert schema["additionalProperties"] is False


def test_additional_properties_nested_objects():
    """Test additionalProperties added recursively to nested objects."""
    schema = {
        "type": "object",
        "properties": {
            "address": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            }
        },
    }
    _add_additional_properties_false(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["address"]["additionalProperties"] is False


def test_additional_properties_array_items():
    """Test additionalProperties added to array item schemas."""
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
        },
    }
    _add_additional_properties_false(schema)
    assert schema["items"]["additionalProperties"] is False


def test_additional_properties_non_object():
    """Test that non-object schemas are left alone."""
    schema = {"type": "string"}
    _add_additional_properties_false(schema)
    assert "additionalProperties" not in schema
