"""Services for Scene Manager."""
import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_AREA_ID,
    CONF_DIRECTION,
    DIRECTION_FORWARD,
    DIRECTION_BACKWARD,
    SERVICE_CYCLE_SCENE,
    SERVICE_TURN_ON_ADAPTIVE,
    CONF_TRANSITION,
)

CYCLE_SCHEMA = vol.Schema({
    vol.Required(CONF_AREA_ID): cv.string,
    vol.Optional(CONF_DIRECTION, default=DIRECTION_FORWARD): vol.In(
        [DIRECTION_FORWARD, DIRECTION_BACKWARD]
    ),
    vol.Optional(CONF_TRANSITION, default=0.5): vol.Coerce(float),
})

ADAPTIVE_SCHEMA = vol.Schema({
    vol.Required(CONF_AREA_ID): cv.string,
    vol.Optional(CONF_TRANSITION, default=0.5): vol.Coerce(float),
})
from .store import SceneManagerStore

_LOGGER = logging.getLogger(__name__)

def resolve_time(hass: HomeAssistant, time_type: str, time_str: str, sun_event: str, offset: int, limit_type: str, limit_time_str: str, target_date, now: datetime) -> datetime | None:
    """Resolve a configured time block to an absolute datetime for a given date."""
    if time_type == "time" and time_str:
        # time_str is like "08:00"
        parsed = dt_util.parse_time(time_str)
        if parsed:
            return dt_util.as_local(datetime.combine(target_date, parsed))
    elif time_type in ("sun", "bounded_sun") and sun_event:
        # sun_event is "sunrise" or "sunset"
        event_time = get_astral_event_date(hass, sun_event, target_date)
        if event_time:
            t = dt_util.as_local(event_time + timedelta(minutes=offset or 0))
            if time_type == "bounded_sun" and limit_type and limit_type != "none" and limit_time_str:
                parsed_limit = dt_util.parse_time(limit_time_str)
                if parsed_limit:
                    limit_dt = dt_util.as_local(datetime.combine(target_date, parsed_limit))
                    if limit_type == "earliest":
                        t = max(t, limit_dt)
                    elif limit_type == "latest":
                        t = min(t, limit_dt)
            return t
    return None

def get_active_schedule_index(hass: HomeAssistant, schedules: list, now: datetime) -> int | None:
    """Return the index of the schedule that is currently active based on the time rules."""
    active_index = None
    best_time = None
    
    for idx, schedule in enumerate(schedules):
        t_today = resolve_time(
            hass,
            schedule.get("start_type"),
            schedule.get("start_time"),
            schedule.get("start_sun_event"),
            schedule.get("start_offset", 0),
            schedule.get("start_limit_type"),
            schedule.get("start_limit_time"),
            now.date(),
            now
        )
        if t_today and t_today <= now:
            if best_time is None or t_today > best_time:
                best_time = t_today
                active_index = idx
                
        t_yesterday = resolve_time(
            hass,
            schedule.get("start_type"),
            schedule.get("start_time"),
            schedule.get("start_sun_event"),
            schedule.get("start_offset", 0),
            schedule.get("start_limit_type"),
            schedule.get("start_limit_time"),
            (now - timedelta(days=1)).date(),
            now
        )
        if t_yesterday and t_yesterday <= now:
            if best_time is None or t_yesterday > best_time:
                best_time = t_yesterday
                active_index = idx
                
    return active_index

async def async_setup_services(hass: HomeAssistant, store: SceneManagerStore):
    """Set up the services for Scene Manager."""
    
    # Store cycle state in memory
    hass.data[DOMAIN]["cycle_state"] = {}

    def get_scenes_for_area(area_id: str) -> list[str]:
        """Return a sorted list of scene entity IDs for a given area based on average brightness."""
        entity_reg = er.async_get(hass)
        scenes = []
        for entity in entity_reg.entities.values():
            if entity.domain == "scene" and entity.area_id == area_id:
                scenes.append(entity.entity_id)
                
        from .light import _get_scene_entity_states, _get_brightness
        
        def _scene_avg_brightness(scene_id: str) -> float:
            states = _get_scene_entity_states(hass, scene_id)
            if not states:
                return 0.0
            
            total_b = 0
            count = 0
            for entity_id, state_dict in states.items():
                if entity_id.startswith("light."):
                    total_b += _get_brightness(state_dict)
                    count += 1
                    
            return (total_b / count) if count > 0 else 0.0
            
        return sorted(scenes, key=_scene_avg_brightness, reverse=True)

    async def handle_cycle_scene(call: ServiceCall):
        area_id = call.data[CONF_AREA_ID]
        direction = call.data.get(CONF_DIRECTION, DIRECTION_FORWARD)
        transition = call.data.get(CONF_TRANSITION)
        
        all_scenes = get_scenes_for_area(area_id)
        rot_config = store.get_rotation_config(area_id)
        excluded_scenes = rot_config.get("excluded_scenes", [])
        scene_order = rot_config.get("scene_order", [])

        # Build scenes list respecting order
        scenes = []
        for s in scene_order:
            if s in all_scenes and s not in excluded_scenes and s not in scenes:
                scenes.append(s)
                
        # Then append any remaining scenes that aren't excluded
        for s in all_scenes:
            if s not in excluded_scenes and s not in scenes:
                scenes.append(s)

        if not scenes:
            _LOGGER.warning("No scenes found for area %s (all excluded or none exist?)", area_id)
            return

        state = hass.data[DOMAIN]["cycle_state"]
        current_scene = state.get(area_id)
        
        try:
            current_idx = scenes.index(current_scene)
        except ValueError:
            current_idx = -1
        
        if direction == DIRECTION_FORWARD:
            next_idx = (current_idx + 1) % len(scenes)
        else:
            if current_idx <= 0:
                next_idx = len(scenes) - 1
            else:
                next_idx = (current_idx - 1) % len(scenes)
                
        scene_to_activate = scenes[next_idx]
        state[area_id] = scene_to_activate
        
        _LOGGER.debug("Activating scene %s (index %s)", scene_to_activate, next_idx)
        
        service_data = {"entity_id": scene_to_activate}
        if transition is not None:
            service_data["transition"] = transition
            
        config = store.get_virtual_light_config(area_id)
        
        await hass.services.async_call(
            "scene", "turn_on", service_data, blocking=True
        )
        
        if config.get("double_trigger"):
            import asyncio
            async def _double_trigger_scene():
                try:
                    await asyncio.sleep(config.get("double_trigger_delay", 0.5))
                    await hass.services.async_call("scene", "turn_on", service_data, blocking=True)
                except asyncio.CancelledError:
                    pass
                    
            if "double_trigger_tasks" not in hass.data[DOMAIN]:
                hass.data[DOMAIN]["double_trigger_tasks"] = {}
                
            if area_id in hass.data[DOMAIN]["double_trigger_tasks"]:
                hass.data[DOMAIN]["double_trigger_tasks"][area_id].cancel()
                
            hass.data[DOMAIN]["double_trigger_tasks"][area_id] = hass.async_create_task(_double_trigger_scene())
            
        hass.bus.async_fire("scene_manager_active_scene_changed", {
            "area_id": area_id,
            "scene_id": scene_to_activate
        })

    async def handle_turn_on_adaptive(call: ServiceCall):
        area_id = call.data[CONF_AREA_ID]
        transition = call.data.get(CONF_TRANSITION)
        schedules = store.get_area_schedules(area_id)
        
        if not schedules:
            _LOGGER.warning("No adaptive schedule found for area %s", area_id)
            return
            
        now = dt_util.now()
        active_idx = get_active_schedule_index(hass, schedules, now)
        active_scene = schedules[active_idx].get("scene_id") if active_idx is not None else None
                
        if active_scene:
            _LOGGER.debug("Adaptive: Activating scene %s for area %s", active_scene, area_id)
            hass.data[DOMAIN]["cycle_state"][area_id] = active_scene
            
            service_data = {"entity_id": active_scene}
            if transition is not None:
                service_data["transition"] = transition
                
            config = store.get_virtual_light_config(area_id)
                
            await hass.services.async_call(
                "scene", "turn_on", service_data, blocking=True
            )
            
            if config.get("double_trigger"):
                import asyncio
                async def _double_trigger_adaptive():
                    try:
                        await asyncio.sleep(config.get("double_trigger_delay", 0.5))
                        await hass.services.async_call("scene", "turn_on", service_data, blocking=True)
                    except asyncio.CancelledError:
                        pass
                        
                if "double_trigger_tasks" not in hass.data[DOMAIN]:
                    hass.data[DOMAIN]["double_trigger_tasks"] = {}
                    
                if area_id in hass.data[DOMAIN]["double_trigger_tasks"]:
                    hass.data[DOMAIN]["double_trigger_tasks"][area_id].cancel()
                    
                hass.data[DOMAIN]["double_trigger_tasks"][area_id] = hass.async_create_task(_double_trigger_adaptive())
                
            hass.bus.async_fire("scene_manager_active_scene_changed", {
                "area_id": area_id,
                "scene_id": active_scene
            })
        else:
            _LOGGER.warning("Adaptive: No matching schedule found for current time for area %s", area_id)

    hass.services.async_register(
        DOMAIN, SERVICE_CYCLE_SCENE, handle_cycle_scene, schema=CYCLE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TURN_ON_ADAPTIVE, handle_turn_on_adaptive, schema=ADAPTIVE_SCHEMA
    )
