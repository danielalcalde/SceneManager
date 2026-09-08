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

def resolve_time(hass: HomeAssistant, time_type: str, time_str: str, sun_event: str, offset: int, now: datetime) -> datetime | None:
    """Resolve a configured time block to an absolute datetime for today."""
    if time_type == "time" and time_str:
        # time_str is like "08:00"
        parsed = dt_util.parse_time(time_str)
        if parsed:
            return dt_util.as_local(datetime.combine(now.date(), parsed))
    elif time_type == "sun" and sun_event:
        # sun_event is "sunrise" or "sunset"
        event_time = get_astral_event_date(hass, sun_event, now.date())
        if event_time:
            return dt_util.as_local(event_time + timedelta(minutes=offset or 0))
    return None

def is_time_in_schedule(hass: HomeAssistant, now: datetime, schedule: dict) -> bool:
    """Check if the current time is within the configured schedule window."""
    start_time = resolve_time(
        hass,
        schedule.get("start_type"),
        schedule.get("start_time"),
        schedule.get("start_sun_event"),
        schedule.get("start_offset", 0),
        now,
    )
    end_time = resolve_time(
        hass,
        schedule.get("end_type"),
        schedule.get("end_time"),
        schedule.get("end_sun_event"),
        schedule.get("end_offset", 0),
        now,
    )
    
    if not start_time or not end_time:
        return False
        
    # Handle wrap around midnight
    if end_time < start_time:
        return now >= start_time or now <= end_time
    else:
        return start_time <= now <= end_time


async def async_setup_services(hass: HomeAssistant, store: SceneManagerStore):
    """Set up the services for Scene Manager."""
    
    # Store cycle state in memory
    hass.data[DOMAIN]["cycle_state"] = {}

    def get_scenes_for_area(area_id: str) -> list[str]:
        """Return a sorted list of scene entity IDs for a given area."""
        entity_reg = er.async_get(hass)
        scenes = []
        for entity in entity_reg.entities.values():
            if entity.domain == "scene" and entity.area_id == area_id:
                scenes.append(entity.entity_id)
        return sorted(scenes)

    async def handle_cycle_scene(call: ServiceCall):
        area_id = call.data[CONF_AREA_ID]
        direction = call.data.get(CONF_DIRECTION, DIRECTION_FORWARD)
        transition = call.data.get(CONF_TRANSITION)
        
        all_scenes = get_scenes_for_area(area_id)
        excluded_scenes = store.get_rotation_config(area_id)
        scenes = [s for s in all_scenes if s not in excluded_scenes]

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
            
        await hass.services.async_call(
            "scene", "turn_on", service_data, blocking=True
        )
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
        active_scene = None
        
        for schedule in schedules:
            if is_time_in_schedule(hass, now, schedule):
                active_scene = schedule.get("scene_id")
                break
                
        if active_scene:
            _LOGGER.debug("Adaptive: Activating scene %s for area %s", active_scene, area_id)
            hass.data[DOMAIN]["cycle_state"][area_id] = active_scene
            
            service_data = {"entity_id": active_scene}
            if transition is not None:
                service_data["transition"] = transition
                
            await hass.services.async_call(
                "scene", "turn_on", service_data, blocking=True
            )
            hass.bus.async_fire("scene_manager_active_scene_changed", {
                "area_id": area_id,
                "scene_id": active_scene
            })
        else:
            _LOGGER.debug("Adaptive: No matching schedule found for current time")

    hass.services.async_register(
        DOMAIN, SERVICE_CYCLE_SCENE, handle_cycle_scene, schema=CYCLE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TURN_ON_ADAPTIVE, handle_turn_on_adaptive, schema=ADAPTIVE_SCHEMA
    )
