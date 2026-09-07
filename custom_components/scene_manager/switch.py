"""Switch platform for Scene Manager."""
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers import area_registry as ar

from .const import DOMAIN, SERVICE_TURN_ON_ADAPTIVE

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the Scene Manager switch platform."""
    store = hass.data[DOMAIN]["store"]
    area_reg = ar.async_get(hass)
    
    from homeassistant.helpers import entity_registry as er
    entity_reg = er.async_get(hass)
    
    area_ids = set(store.data.get("areas", {}).keys())
    for entity in entity_reg.entities.values():
        if entity.domain == "scene" and entity.area_id:
            area_ids.add(entity.area_id)
    
    entities = []
    # Create a virtual switch for every area that has scenes or is configured
    for area_id in area_ids:
        area = area_reg.async_get_area(area_id)
        area_name = area.name if area else area_id
        entities.append(AdaptiveSceneSwitch(hass, area_id, area_name))
        
    async_add_entities(entities)
    
    known_areas = set(area_ids)

    from homeassistant.core import Event, callback

    @callback
    def _async_entity_registry_updated(event: Event) -> None:
        if event.data.get("action") == "create":
            entity_id = event.data.get("entity_id")
            if entity_id and entity_id.startswith("scene."):
                entity = entity_reg.async_get(entity_id)
                if entity and entity.area_id and entity.area_id not in known_areas:
                    known_areas.add(entity.area_id)
                    area = area_reg.async_get_area(entity.area_id)
                    area_name = area.name if area else entity.area_id
                    async_add_entities([AdaptiveSceneSwitch(hass, entity.area_id, area_name)])
                    
    hass.bus.async_listen("entity_registry_updated", _async_entity_registry_updated)
    
    @callback
    def _async_area_configured(event: Event) -> None:
        area_id = event.data.get("area_id")
        if area_id and area_id not in known_areas:
            known_areas.add(area_id)
            area = area_reg.async_get_area(area_id)
            area_name = area.name if area else area_id
            async_add_entities([AdaptiveSceneSwitch(hass, area_id, area_name)])
            
    hass.bus.async_listen("scene_manager_area_configured", _async_area_configured)

class AdaptiveSceneSwitch(SwitchEntity):
    """Virtual switch to trigger adaptive scenes for an area."""

    def __init__(self, hass: HomeAssistant, area_id: str, area_name: str):
        """Initialize the switch."""
        self.hass = hass
        self._area_id = area_id
        self._attr_name = f"{area_name} Adaptive Lights"
        self._attr_unique_id = f"scene_manager_adaptive_{area_id}"
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        """Turn the switch on, triggering the adaptive scene."""
        await self.hass.services.async_call(
            DOMAIN, SERVICE_TURN_ON_ADAPTIVE, {"area_id": self._area_id}
        )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off, turning off all lights in the area."""
        await self.hass.services.async_call(
            "light", "turn_off", {"area_id": self._area_id}
        )
        self._attr_is_on = False
        self.async_write_ha_state()
