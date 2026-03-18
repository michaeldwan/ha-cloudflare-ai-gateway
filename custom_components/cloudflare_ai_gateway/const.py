"""Constants for the Cloudflare AI Gateway integration."""

import logging

DOMAIN = "cloudflare_ai_gateway"
LOGGER: logging.Logger = logging.getLogger(__package__)

# Config keys - parent entry (gateway credentials)
CONF_ACCOUNT_ID = "account_id"
CONF_GATEWAY_ID = "gateway_id"
CONF_CF_API_TOKEN = "cf_api_token"

# Subentry type
SUBENTRY_TYPE_MODEL = "model"

# Model types (stored in subentry data)
MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_IMAGE = "image"

# Config keys - subentry (per-model settings)
CONF_MODEL_TYPE = "model_type"
CONF_PROVIDER = "provider"
CONF_CHAT_MODEL = "chat_model"
CONF_MAX_TOKENS = "max_tokens"
CONF_PROMPT = "prompt"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_RECOMMENDED = "recommended"

# Config keys - image model
CONF_IMAGE_MODEL = "image_model"
CONF_IMAGE_WIDTH = "image_width"
CONF_IMAGE_HEIGHT = "image_height"
CONF_IMAGE_STEPS = "image_steps"

# Cloudflare-specific config keys
CONF_CACHE_TTL = "cache_ttl"

# Defaults
DEFAULT_GATEWAY_ID = "default"
DEFAULT_PROVIDER = "openai"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"

DEFAULT_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
DEFAULT_IMAGE_WIDTH = 1024
DEFAULT_IMAGE_HEIGHT = 1024
DEFAULT_IMAGE_STEPS = 4

# Workers AI model prefixes (used for model validation)
WORKERS_AI_MODEL_PREFIXES = ("@cf/", "@hf/")

RECOMMENDED_MAX_TOKENS = 3000
RECOMMENDED_TEMPERATURE = 1.0
RECOMMENDED_TOP_P = 1.0

# Supported providers on Cloudflare AI Gateway
SUPPORTED_PROVIDERS = [
    "anthropic",
    "aws-bedrock",
    "azure-openai",
    "cohere",
    "deepseek",
    "google-ai-studio",
    "grok",
    "groq",
    "huggingface",
    "mistral",
    "moonshotai",
    "openai",
    "perplexity-ai",
    "together-ai",
    "workers-ai",
]

# Supported Workers AI image generation models
SUPPORTED_IMAGE_MODELS = [
    "@cf/black-forest-labs/flux-1-schnell",
    "@cf/stabilityai/stable-diffusion-xl-base-1.0",
    "@cf/bytedance/stable-diffusion-xl-lightning",
    "@cf/lykon/dreamshaper-8-lcm",
]
