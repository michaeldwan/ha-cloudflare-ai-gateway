# CLAUDE.md

## Project

Home Assistant custom integration for Cloudflare AI Gateway. Routes conversation agents through Cloudflare's unified AI gateway endpoint, supporting 15+ providers with a single config.

## Dev Setup

- `mise install` — install Python 3.13 and uv
- `uv sync` — install dependencies
- `mise run validate` — **run this before every commit** (lint + format + tests)

## Commands

- `mise run validate` — lint, format check, and tests (same as CI)
- `mise run test` — run tests only
- `mise run lint` — ruff check + format check
- `mise run format` — auto-format code
- `mise run develop` — start HA in Docker with integration loaded (http://localhost:8123)

## Architecture

- **Parent config entry** = Cloudflare gateway (account ID, gateway ID, CF API token)
- **Subentries** = individual models, each becomes a conversation agent
- **Universal/BYOK auth** — CF token in Authorization header, Cloudflare injects stored provider keys
- Base LLM logic in `entity.py`, platform-specific code in `conversation.py`
- Designed to add AI Task, TTS, STT later without redesign (new platform file + subentry type)

## Key Files

- `custom_components/cloudflare_ai_gateway/entity.py` — base entity with Chat Completions streaming + tool calling
- `custom_components/cloudflare_ai_gateway/conversation.py` — conversation platform
- `custom_components/cloudflare_ai_gateway/config_flow.py` — setup flow + subentry flow
- `tests/components/cloudflare_ai_gateway/conftest.py` — test fixtures
