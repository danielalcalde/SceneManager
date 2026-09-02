"""Light platform for Scene Manager."""
import logging
import os
from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers import area_registry as ar
from homeassistant.util.yaml import load_yaml
from homeassistant.util import slugify

from .const import DOMAIN, SERVICE_TURN_ON_ADAPTIVE

_LOGGER = logging.getLogger(__name__)

def _get_scene_entity_states(hass: HomeAssistant, scene_id: str) -> dict:
    """Read scenes.yaml and return the entity states for a given scene."""
    path = hass.config.path("scenes.yaml")
    if not os.path.exists(path):
        return {}
    try:
        scenes = load_yaml(path)
        if not scenes or not isinstance(scenes, list):
            return {}
        for scene in scenes:
            name = scene.get("name", "")
            if f"scene.{slugify(name)}" == scene_id or scene.get("id") == scene_id.replace("scene.", ""):
                return scene.get("entities", {})
    except Exception as e:
        _LOGGER.error("Error reading scenes.yaml: %s", e)
    return {}

def _interpolate_value(val1, val2, fraction):
    if val1 is None or val2 is None:
        return val1 if val1 is not None else val2
    return type(val1)(val1 + (val2 - val1) * fraction)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the Scene Manager light platform."""
    store = hass.data[DOMAIN]["store"]
    area_reg = ar.async_get(hass)
    
    entities = []
    for area_id in store.data.get("areas", {}):
        area = area_reg.async_get_area(area_id)
        area_name = area.name if area else area_id
        entities.append(AdaptiveSceneLight(hass, area_id, area_name))
        
    async_add_entities(entities)

class AdaptiveSceneLight(LightEntity):
    """Virtual light to trigger adaptive scenes or interpolate scenes for an area."""

    def __init__(self, hass: HomeAssistant, area_id: str, area_name: str):
        """Initialize the light."""
        self.hass = hass
        self._area_id = area_id
        self._attr_name = f"{area_name} Adaptive Lights"
        self._attr_unique_id = f"scene_manager_light_virtual_{area_id}"
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_is_on = False
        self._attr_brightness = 255

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        config = self.hass.data[DOMAIN]["store"].get_virtual_light_config(self._area_id)
        return config.get("enabled", True)

    async def async_turn_on(self, **kwargs):
        """Turn the light on, triggering adaptive scene or specific brightness."""
        transition = kwargs.get(ATTR_TRANSITION)
        config = self.hass.data[DOMAIN]["store"].get_virtual_light_config(self._area_id)
        
        if ATTR_BRIGHTNESS in kwargs and config.get("interpolation_enabled"):
            target_pct = kwargs[ATTR_BRIGHTNESS] / 255.0 * 100.0
            mapping = config.get("mapping", {})
            if len(mapping) >= 2:
                # Sort scenes by percentage
                sorted_scenes = sorted(mapping.items(), key=lambda x: x[1])
                
                lower = sorted_scenes[0]
                upper = sorted_scenes[-1]
                for scene_id, pct in sorted_scenes:
                    if pct <= target_pct:
                        lower = (scene_id, pct)
                for scene_id, pct in reversed(sorted_scenes):
                    if pct >= target_pct:
                        upper = (scene_id, pct)

                fraction = 0
                if upper[1] > lower[1]:
                    fraction = (target_pct - lower[1]) / (upper[1] - lower[1])

                lower_states = await self.hass.async_add_executor_job(_get_scene_entity_states, self.hass, lower[0])
                upper_states = await self.hass.async_add_executor_job(_get_scene_entity_states, self.hass, upper[0])

                if lower_states and upper_states:
                    for entity_id, lower_state in lower_states.items():
                        upper_state = upper_states.get(entity_id)
                        if not upper_state:
                            continue
                        
                        service_data = {"entity_id": entity_id}
                        if transition is not None:
                            service_data["transition"] = transition

                        if lower_state.get("state") == "off" and upper_state.get("state") == "off":
                            await self.hass.services.async_call("light", "turn_off", service_data)
                            continue

                        lb = lower_state.get("brightness", 0 if lower_state.get("state") == "off" else 255)
                        ub = upper_state.get("brightness", 0 if upper_state.get("state") == "off" else 255)
                        
                        target_b = _interpolate_value(lb, ub, fraction)
                        service_data["brightness"] = int(target_b)

                        color_mode = lower_state.get("color_mode", upper_state.get("color_mode"))
                        
                        if color_mode == "color_temp":
                            if "color_temp_kelvin" in lower_state and "color_temp_kelvin" in upper_state:
                                service_data["color_temp_kelvin"] = int(_interpolate_value(lower_state["color_temp_kelvin"], upper_state["color_temp_kelvin"], fraction))
                            elif "color_temp" in lower_state and "color_temp" in upper_state:
                                service_data["color_temp"] = int(_interpolate_value(lower_state["color_temp"], upper_state["color_temp"], fraction))
                        elif color_mode in ("hs", "xy", "rgb", "rgbw", "rgbww"):
                            if "rgb_color" in lower_state and "rgb_color" in upper_state:
                                lr, lg, lb_c = lower_state["rgb_color"]
                                ur, ug, ub_c = upper_state["rgb_color"]
                                service_data["rgb_color"] = [
                                    int(_interpolate_value(lr, ur, fraction)),
                                    int(_interpolate_value(lg, ug, fraction)),
                                    int(_interpolate_value(lb_c, ub_c, fraction))
                                ]
                        else:
                            # Fallback if color_mode is missing
                            if "color_temp_kelvin" in lower_state and "color_temp_kelvin" in upper_state:
                                service_data["color_temp_kelvin"] = int(_interpolate_value(lower_state["color_temp_kelvin"], upper_state["color_temp_kelvin"], fraction))
                            elif "color_temp" in lower_state and "color_temp" in upper_state:
                                service_data["color_temp"] = int(_interpolate_value(lower_state["color_temp"], upper_state["color_temp"], fraction))
                            elif "rgb_color" in lower_state and "rgb_color" in upper_state:
                                lr, lg, lb_c = lower_state["rgb_color"]
                                ur, ug, ub_c = upper_state["rgb_color"]
                                service_data["rgb_color"] = [
                                    int(_interpolate_value(lr, ur, fraction)),
                                    int(_interpolate_value(lg, ug, fraction)),
                                    int(_interpolate_value(lb_c, ub_c, fraction))
                                ]

                        if service_data.get("brightness", 1) > 0:
                            await self.hass.services.async_call("light", "turn_on", service_data)
                        else:
                            await self.hass.services.async_call("light", "turn_off", {"entity_id": entity_id})
                    
                    self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
                    self._attr_is_on = True
                    self.async_write_ha_state()
                    return

        # Fallback if interpolation is off, mapping is invalid, or no brightness provided
        if ATTR_BRIGHTNESS in kwargs:
            data = {"brightness": kwargs[ATTR_BRIGHTNESS]}
            if transition is not None:
                data["transition"] = transition
            await self.hass.services.async_call("light", "turn_on", data, target={"area_id": self._area_id})
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        else:
            data = {"area_id": self._area_id}
            if transition is not None:
                data["transition"] = transition
            await self.hass.services.async_call(DOMAIN, SERVICE_TURN_ON_ADAPTIVE, data)
            
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the light off, turning off all lights in the area."""
        data = {}
        transition = kwargs.get(ATTR_TRANSITION)
        if transition is not None:
            data["transition"] = transition
            
        await self.hass.services.async_call(
            "light", "turn_off", data, target={"area_id": self._area_id}
        )
        self._attr_is_on = False
        self.async_write_ha_state()
