"""Constants for the Cloudflare AI Gateway integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.helpers.storage import Store
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

DOMAIN = "cloudflare_ai_gateway"
LOGGER: logging.Logger = logging.getLogger(__package__)

# Config keys - parent entry (gateway credentials)
CONF_ACCOUNT_ID = "account_id"
CONF_GATEWAY_ID = "gateway_id"
CONF_CF_API_TOKEN = "cf_api_token"

# Subentry types (one per platform capability)
SUBENTRY_TYPE_CONVERSATION = "conversation"
SUBENTRY_TYPE_AI_TASK_DATA = "ai_task_data"
SUBENTRY_TYPE_AI_TASK_IMAGE = "ai_task_image"

# Subentry types that get usage tracking sensors
CHAT_SUBENTRY_TYPES = (SUBENTRY_TYPE_CONVERSATION, SUBENTRY_TYPE_AI_TASK_DATA)
TRACKED_SUBENTRY_TYPES = (*CHAT_SUBENTRY_TYPES, SUBENTRY_TYPE_AI_TASK_IMAGE)

# Config keys - subentry (per-model settings)
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
DEFAULT_PROVIDER = "workers-ai"
DEFAULT_CONVERSATION_MODEL = "@cf/zai-org/glm-4.7-flash"
DEFAULT_AI_TASK_DATA_MODEL = "@cf/moonshotai/kimi-k2.5"

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

# Dispatcher signal for sensor updates
SIGNAL_MODEL_STATS_UPDATED = f"{DOMAIN}_stats_updated_{{subentry_id}}"

# Storage key for persisting model stats
STORAGE_KEY_STATS = f"{DOMAIN}_{{entry_id}}_stats"
STORAGE_VERSION = 1


@dataclass
class ModelStats:
    """Accumulated usage statistics for a single model."""

    total_requests: int = 0
    total_errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0


@dataclass
class CloudflareAIGatewayRuntimeData:
    """Runtime data shared across platforms for a config entry."""

    model_stats: dict[str, ModelStats] = field(default_factory=dict)
    store: Store[dict[str, dict[str, Any]]] | None = field(default=None, repr=False)
    analytics_coordinator: DataUpdateCoordinator[float | None] | None = field(default=None, repr=False)


# Supported Workers AI image generation models
SUPPORTED_IMAGE_MODELS = [
    "@cf/black-forest-labs/flux-1-schnell",
    "@cf/stabilityai/stable-diffusion-xl-base-1.0",
    "@cf/bytedance/stable-diffusion-xl-lightning",
    "@cf/lykon/dreamshaper-8-lcm",
]
