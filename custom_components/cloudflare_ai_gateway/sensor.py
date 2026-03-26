"""Sensor platform for Cloudflare AI Gateway usage monitoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CloudflareAIGatewayConfigEntry
from .const import CHAT_SUBENTRY_TYPES, DOMAIN, SIGNAL_MODEL_STATS_UPDATED, SUBENTRY_TYPE_AI_TASK_IMAGE, ModelStats


@dataclass(frozen=True, kw_only=True)
class CloudflareAIGatewaySensorDescription(SensorEntityDescription):
    """Sensor entity description for Cloudflare AI Gateway."""

    value_fn: Callable[[ModelStats], int]


# Sensors available for all model types
BASE_SENSOR_DESCRIPTIONS: tuple[CloudflareAIGatewaySensorDescription, ...] = (
    CloudflareAIGatewaySensorDescription(
        key="requests",
        translation_key="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="requests",
        value_fn=lambda stats: stats.total_requests,
    ),
    CloudflareAIGatewaySensorDescription(
        key="errors",
        translation_key="errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="errors",
        value_fn=lambda stats: stats.total_errors,
    ),
)

# Additional sensors for chat models (tokens + cache)
CHAT_SENSOR_DESCRIPTIONS: tuple[CloudflareAIGatewaySensorDescription, ...] = (
    CloudflareAIGatewaySensorDescription(
        key="input_tokens",
        translation_key="input_tokens",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="tokens",
        value_fn=lambda stats: stats.input_tokens,
    ),
    CloudflareAIGatewaySensorDescription(
        key="output_tokens",
        translation_key="output_tokens",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="tokens",
        value_fn=lambda stats: stats.output_tokens,
    ),
    CloudflareAIGatewaySensorDescription(
        key="cache_hits",
        translation_key="cache_hits",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="requests",
        value_fn=lambda stats: stats.cache_hits,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CloudflareAIGatewayConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities for each subentry."""
    for subentry in entry.subentries.values():
        if subentry.subentry_type in CHAT_SUBENTRY_TYPES:
            descriptions = BASE_SENSOR_DESCRIPTIONS + CHAT_SENSOR_DESCRIPTIONS
        elif subentry.subentry_type == SUBENTRY_TYPE_AI_TASK_IMAGE:
            descriptions = BASE_SENSOR_DESCRIPTIONS
        else:
            continue

        async_add_entities(
            [
                CloudflareAIGatewayUsageSensor(
                    entry=entry,
                    subentry_id=subentry.subentry_id,
                    description=description,
                )
                for description in descriptions
            ],
            config_subentry_id=subentry.subentry_id,
        )


class CloudflareAIGatewayUsageSensor(SensorEntity):
    """Sensor exposing accumulated usage stats for a model."""

    _attr_has_entity_name = True
    entity_description: CloudflareAIGatewaySensorDescription

    def __init__(
        self,
        entry: CloudflareAIGatewayConfigEntry,
        subentry_id: str,
        description: CloudflareAIGatewaySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._entry = entry
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
        )

    @property
    def native_value(self) -> int:
        """Return the current sensor value."""
        stats = self._entry.runtime_data.model_stats.get(self._subentry_id)
        if stats is None:
            return 0
        return self.entity_description.value_fn(stats)

    async def async_added_to_hass(self) -> None:
        """Register dispatcher listener for stats updates."""
        signal = SIGNAL_MODEL_STATS_UPDATED.format(subentry_id=self._subentry_id)
        self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._handle_stats_update))

    @callback
    def _handle_stats_update(self) -> None:
        """Handle updated stats from the LLM entity."""
        self.async_write_ha_state()
