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
    
    entities = []
    # Create a virtual switch for every configured area
    for area_id in store.data.get("areas", {}):
        area = area_reg.async_get_area(area_id)
        area_name = area.name if area else area_id
        entities.append(AdaptiveSceneSwitch(hass, area_id, area_name))
        
    async_add_entities(entities)

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
