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

def _get_brightness(state_dict):
    """Get brightness from a state dict, defaulting appropriately if missing."""
    b = state_dict.get("brightness")
    if b is None:
        return 0 if state_dict.get("state") == "off" else 255
    return b

def _apply_interpolated_attribute(service_data, attr_name, lower_state, upper_state, fraction):
    """Interpolate an attribute (scalar or list) and add it to service_data."""
    if attr_name in lower_state and attr_name in upper_state:
        val1 = lower_state[attr_name]
        val2 = upper_state[attr_name]
        if isinstance(val1, (list, tuple)) and isinstance(val2, (list, tuple)) and len(val1) == len(val2):
            service_data[attr_name] = [int(_interpolate_value(v1, v2, fraction)) for v1, v2 in zip(val1, val2)]
        else:
            service_data[attr_name] = int(_interpolate_value(val1, val2, fraction))
    elif attr_name in upper_state and lower_state.get("state") == "off":
        service_data[attr_name] = upper_state[attr_name]
    elif attr_name in lower_state and upper_state.get("state") == "off":
        service_data[attr_name] = lower_state[attr_name]

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the Scene Manager light platform."""
    store = hass.data[DOMAIN]["store"]
    area_reg = ar.async_get(hass)
    
    from homeassistant.helpers import entity_registry as er
    entity_reg = er.async_get(hass)
    
    area_ids = set(store.data.get("areas", {}).keys())
    for entity in entity_reg.entities.values():
        if entity.domain == "scene" and entity.area_id:
            area_ids.add(entity.area_id)
            
    entities = []
    for area_id in area_ids:
        area = area_reg.async_get_area(area_id)
        area_name = area.name if area else area_id
        entities.append(AdaptiveSceneLight(hass, area_id, area_name))
        
    async_add_entities(entities)
    
    known_areas = set(area_ids)

    from homeassistant.core import Event, callback

    def _add_area_light(area_id: str) -> None:
        if area_id and area_id not in known_areas:
            known_areas.add(area_id)
            area = area_reg.async_get_area(area_id)
            area_name = area.name if area else area_id
            async_add_entities([AdaptiveSceneLight(hass, area_id, area_name)])

    @callback
    def _async_entity_registry_updated(event: Event) -> None:
        if event.data.get("action") == "create":
            entity_id = event.data.get("entity_id")
            if entity_id and entity_id.startswith("scene."):
                entity = entity_reg.async_get(entity_id)
                if entity and entity.area_id:
                    _add_area_light(entity.area_id)
                    
    hass.bus.async_listen("entity_registry_updated", _async_entity_registry_updated)
    
    @callback
    def _async_area_configured(event: Event) -> None:
        area_id = event.data.get("area_id")
        _add_area_light(area_id)
            
    hass.bus.async_listen("scene_manager_area_configured", _async_area_configured)

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
        self._light_entities = []
        self._interpolated_brightness = None
        self._last_interaction_time = 0

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        from homeassistant.helpers import entity_registry as er
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers.event import async_track_state_change_event
        from homeassistant.core import callback

        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        
        devices_in_area = {
            device.id
            for device in device_reg.devices.values()
            if device.area_id == self._area_id
        }
        
        self._light_entities = []
        for entity in entity_reg.entities.values():
            if entity.domain == "light" and entity.entity_id != self.entity_id:
                if entity.area_id == self._area_id or (entity.area_id is None and entity.device_id in devices_in_area):
                    self._light_entities.append(entity.entity_id)
                    
        _LOGGER.warning("SceneManager Light %s tracking entities: %s", self._area_id, self._light_entities)

        @callback
        def _async_light_state_changed(event):
            import time
            if time.time() - getattr(self, "_last_interaction_time", 0) > 3:
                self._interpolated_brightness = None
            self._update_state_from_lights()
            self.async_write_ha_state()

        @callback
        def _async_scene_changed(event):
            if event.data.get("area_id") == self._area_id:
                import time
                self._last_interaction_time = time.time()
                scene_id = event.data.get("scene_id")
                config = self.hass.data[DOMAIN]["store"].get_virtual_light_config(self._area_id)
                if config.get("interpolation_enabled"):
                    mapping = config.get("mapping", {})
                    if scene_id in mapping:
                        self._interpolated_brightness = int((mapping[scene_id] / 100.0) * 255)
                    else:
                        self._interpolated_brightness = None
                else:
                    self._interpolated_brightness = None
                    
                self._update_state_from_lights()
                self.async_write_ha_state()

        if self._light_entities:
            self._update_state_from_lights()
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, self._light_entities, _async_light_state_changed
                )
            )
            
        self.async_on_remove(
            self.hass.bus.async_listen("scene_manager_active_scene_changed", _async_scene_changed)
        )

    def _update_state_from_lights(self):
        """Update is_on based on child lights in the area."""
        if not getattr(self, "_light_entities", None):
            return
            
        any_on = False
        total_brightness = 0
        on_count = 0
        for entity_id in self._light_entities:
            state = self.hass.states.get(entity_id)
            if state and state.state == "on":
                any_on = True
                total_brightness += state.attributes.get(ATTR_BRIGHTNESS, 255)
                on_count += 1
                
        self._attr_is_on = any_on
        
        if not any_on:
            self._attr_brightness = None
            return
            
        if self._interpolated_brightness is not None:
            self._attr_brightness = self._interpolated_brightness
            return
            
        if on_count > 0:
            self._attr_brightness = int(total_brightness / on_count)
            
        _LOGGER.warning("SceneManager Light %s calculated brightness: %s", self._area_id, self._attr_brightness)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        config = self.hass.data[DOMAIN]["store"].get_virtual_light_config(self._area_id)
        return config.get("enabled", True)

    async def async_turn_on(self, **kwargs):
        """Turn the light on, triggering adaptive scene or specific brightness."""
        import time
        self._last_interaction_time = time.time()
        
        transition = kwargs.get(ATTR_TRANSITION)
        config = self.hass.data[DOMAIN]["store"].get_virtual_light_config(self._area_id)
        
        if ATTR_BRIGHTNESS in kwargs and config.get("interpolation_enabled"):
            self._interpolated_brightness = kwargs[ATTR_BRIGHTNESS]
            
            # Clear active scene so it tracks our new interpolated value
            if "cycle_state" in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN]["cycle_state"].pop(self._area_id, None)
                
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

                if lower_states or upper_states:
                    all_entities = set(lower_states.keys()) | set(upper_states.keys())
                    calls = []
                    
                    for entity_id in all_entities:
                        lower_state = lower_states.get(entity_id, {"state": "off"})
                        upper_state = upper_states.get(entity_id, {"state": "off"})
                        
                        service_data = {"entity_id": entity_id}
                        if transition is not None:
                            service_data["transition"] = transition

                        if lower_state.get("state") == "off" and upper_state.get("state") == "off":
                            calls.append(("light", "turn_off", service_data, None))
                            continue

                        lb = _get_brightness(lower_state)
                        ub = _get_brightness(upper_state)
                        
                        target_b = int(_interpolate_value(lb, ub, fraction))
                        
                        if target_b == 0:
                            turn_off_data = {"entity_id": entity_id}
                            if transition is not None:
                                turn_off_data["transition"] = transition
                            calls.append(("light", "turn_off", turn_off_data, None))
                            continue
                            
                        service_data["brightness"] = target_b

                        color_mode = lower_state.get("color_mode", upper_state.get("color_mode"))
                        
                        if color_mode == "color_temp":
                            _apply_interpolated_attribute(service_data, "color_temp_kelvin", lower_state, upper_state, fraction)
                            _apply_interpolated_attribute(service_data, "color_temp", lower_state, upper_state, fraction)
                        elif color_mode in ("hs", "xy", "rgb", "rgbw", "rgbww"):
                            _apply_interpolated_attribute(service_data, "rgb_color", lower_state, upper_state, fraction)
                        else:
                            # Fallback if color_mode is missing
                            _apply_interpolated_attribute(service_data, "color_temp_kelvin", lower_state, upper_state, fraction)
                            _apply_interpolated_attribute(service_data, "color_temp", lower_state, upper_state, fraction)
                            _apply_interpolated_attribute(service_data, "rgb_color", lower_state, upper_state, fraction)

                        if service_data.get("brightness", 1) > 0:
                            calls.append(("light", "turn_on", service_data, None))
                        else:
                            calls.append(("light", "turn_off", {"entity_id": entity_id}, None))
                    
                    if getattr(self, "_active_task", None):
                        self._active_task.cancel()
                                
                    self._active_task = self.hass.async_create_task(self._async_execute_calls(calls, config))
                    
                    self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
                    self._attr_is_on = True
                    self.async_write_ha_state()
                    return

        # Fallback if interpolation is off, mapping is invalid, or no brightness provided
        calls = []
        if ATTR_BRIGHTNESS in kwargs:
            data = {"brightness": kwargs[ATTR_BRIGHTNESS]}
            if transition is not None:
                data["transition"] = transition
            calls.append(("light", "turn_on", data, {"area_id": self._area_id}))
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        else:
            data = {"area_id": self._area_id}
            if transition is not None:
                data["transition"] = transition
            calls.append((DOMAIN, SERVICE_TURN_ON_ADAPTIVE, data, None))
            
        if getattr(self, "_active_task", None):
            self._active_task.cancel()
            
        self._active_task = self.hass.async_create_task(self._async_execute_calls(calls, config))
            
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

    async def _async_execute_calls(self, calls, config):
        """Execute a list of service calls."""
        import asyncio
        try:
            await asyncio.sleep(0.1)  # 100ms debounce for Alexa rapid commands
            async def _run_calls():
                for domain, svc, svc_data, target in calls:
                    if target:
                        await self.hass.services.async_call(domain, svc, svc_data, target=target)
                    else:
                        await self.hass.services.async_call(domain, svc, svc_data)

            await _run_calls()
                    
            if config.get("double_trigger"):
                await asyncio.sleep(config.get("double_trigger_delay", 0.5))
                await _run_calls()
        except asyncio.CancelledError:
            pass
