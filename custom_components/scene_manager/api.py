"""WebSocket API for Scene Manager."""
import logging
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

@callback
def async_setup_api(hass: HomeAssistant):
    """Set up the Scene Manager WebSocket API."""
    websocket_api.async_register_command(hass, ws_get_schedules)
    websocket_api.async_register_command(hass, ws_save_schedules)
    websocket_api.async_register_command(hass, ws_get_rotation_state)
    websocket_api.async_register_command(hass, ws_save_rotation_config)
    websocket_api.async_register_command(hass, ws_get_virtual_light_config)
    websocket_api.async_register_command(hass, ws_save_virtual_light_config)

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/get_schedules",
    vol.Required("area_id"): str,
})
@callback
def ws_get_schedules(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle get schedules command."""
    store = hass.data[DOMAIN]["store"]
    schedules = store.get_area_schedules(msg["area_id"])
    connection.send_result(msg["id"], schedules)

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/save_schedules",
    vol.Required("area_id"): str,
    vol.Required("schedules"): list,
})
@websocket_api.async_response
async def ws_save_schedules(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle save schedules command."""
    store = hass.data[DOMAIN]["store"]
    await store.async_update_area_schedules(msg["area_id"], msg["schedules"])
    hass.bus.async_fire("scene_manager_area_configured", {"area_id": msg["area_id"]})
    connection.send_result(msg["id"], {"success": True})

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/get_rotation_state",
    vol.Required("area_id"): str,
})
@callback
def ws_get_rotation_state(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle get rotation state command."""
    store = hass.data[DOMAIN]["store"]
    area_id = msg["area_id"]
    rot_config = store.get_rotation_config(area_id)
    current = hass.data[DOMAIN]["cycle_state"].get(area_id)
    connection.send_result(msg["id"], {
        "excluded_scenes": rot_config.get("excluded_scenes", []),
        "scene_order": rot_config.get("scene_order", []),
        "current_scene_id": current
    })

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/save_rotation_config",
    vol.Required("area_id"): str,
    vol.Optional("excluded_scenes"): list,
    vol.Optional("scene_order"): list,
})
@websocket_api.async_response
async def ws_save_rotation_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle save rotation config command."""
    store = hass.data[DOMAIN]["store"]
    config = {
        "excluded_scenes": msg.get("excluded_scenes", []),
        "scene_order": msg.get("scene_order", [])
    }
    await store.async_update_rotation_config(msg["area_id"], config)
    hass.bus.async_fire("scene_manager_area_configured", {"area_id": msg["area_id"]})
    connection.send_result(msg["id"], {"success": True})

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/get_virtual_light_config",
    vol.Required("area_id"): str,
})
@callback
def ws_get_virtual_light_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle get virtual light config command."""
    store = hass.data[DOMAIN]["store"]
    config = store.get_virtual_light_config(msg["area_id"])
    connection.send_result(msg["id"], config)

@websocket_api.websocket_command({
    vol.Required("type"): "scene_manager/save_virtual_light_config",
    vol.Required("area_id"): str,
    vol.Required("config"): dict,
})
@websocket_api.async_response
async def ws_save_virtual_light_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Handle save virtual light config command."""
    store = hass.data[DOMAIN]["store"]
    await store.async_update_virtual_light_config(msg["area_id"], msg["config"])
    hass.bus.async_fire("scene_manager_area_configured", {"area_id": msg["area_id"]})
    connection.send_result(msg["id"], {"success": True})
