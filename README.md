# Cloudflare AI Gateway for Home Assistant

[![Validate](https://github.com/michaeldwan/ha-cloudflare-ai-gateway/actions/workflows/validate.yml/badge.svg)](https://github.com/michaeldwan/ha-cloudflare-ai-gateway/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

A [Home Assistant](https://www.home-assistant.io/) custom integration that routes conversation agents through [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/) -- one config, 15+ providers.

## Supported Providers

Anthropic, AWS Bedrock, Azure OpenAI, Cohere, DeepSeek, Google AI Studio, Grok, Groq, Hugging Face, Mistral, Moonshot AI, OpenAI, Perplexity AI, Together AI, Workers AI — plus any provider you type in manually.

## Features

- **Multiple conversation agents** — add as many models as you want, each becomes a selectable agent in HA
- **Streaming responses** — real-time token streaming in the HA UI
- **Tool calling** — models can control your Home Assistant via the Assist API
- **Universal auth** — one Cloudflare API token, provider keys stored in Cloudflare
- **Response caching** — optional TTL-based caching via Cloudflare AI Gateway

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "Cloudflare AI Gateway"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → Cloudflare AI Gateway

### Manual

Copy `custom_components/cloudflare_ai_gateway/` to your Home Assistant `config/custom_components/` directory.

## Configuration

1. **Add the integration** with your Cloudflare account ID, gateway ID, and API token
2. **Add conversation agents** — click the integration, then "Add conversation agent" to configure a provider and model
3. **Assign agents** — use your agents in voice assistants, automations, or the chat UI

## How it works

The integration creates a **parent config entry** for your Cloudflare gateway credentials (account ID, gateway ID, API token). Each model you add becomes a **subentry** -- its own conversation agent in Home Assistant. Cloudflare handles provider auth, so you store provider API keys in your [AI Gateway settings](https://developers.cloudflare.com/ai-gateway/providers/) and don't need them in HA.

## Development

```bash
mise install          # Python 3.13 + uv
uv sync               # Install dependencies
mise run validate     # Lint + format + tests (run before committing)
mise run develop      # Start HA in Docker at http://localhost:8123
```

## Contributing

Run `mise run validate` before opening a PR -- it's the same check CI runs. That's lint, format, and tests in one shot.

## License

MIT
