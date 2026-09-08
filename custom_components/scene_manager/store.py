"""Storage for Scene Manager."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

class SceneManagerStore:
    """Class to hold Scene Manager configuration data."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the storage."""
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data = {"areas": {}, "rotation": {}}

    async def async_load(self):
        """Load data from storage."""
        stored = await self.store.async_load()
        if stored:
            self.data = stored
            if "rotation" not in self.data:
                self.data["rotation"] = {}
            if "virtual_light" not in self.data:
                self.data["virtual_light"] = {}
        else:
            self.data = {"areas": {}, "rotation": {}, "virtual_light": {}}
        _LOGGER.debug("Loaded Scene Manager data: %s", self.data)

    async def async_save(self):
        """Save data to storage."""
        await self.store.async_save(self.data)
        _LOGGER.debug("Saved Scene Manager data.")

    def get_area_schedules(self, area_id: str) -> list:
        """Get schedules for an area."""
        return self.data["areas"].get(area_id, [])

    async def async_update_area_schedules(self, area_id: str, schedules: list):
        """Update schedules for an area and save."""
        self.data["areas"][area_id] = schedules
        await self.async_save()

    def get_rotation_config(self, area_id: str) -> dict:
        """Get rotation config for an area."""
        data = self.data["rotation"].get(area_id, {})
        if isinstance(data, list):
            return {"excluded_scenes": data, "scene_order": []}
        return {
            "excluded_scenes": data.get("excluded_scenes", []),
            "scene_order": data.get("scene_order", [])
        }

    async def async_update_rotation_config(self, area_id: str, config: dict):
        """Update rotation config for an area and save."""
        self.data["rotation"][area_id] = config
        await self.async_save()
    def get_virtual_light_config(self, area_id: str) -> dict:
        """Get virtual light config for an area."""
        return self.data["virtual_light"].get(area_id, {
            "enabled": True,
            "interpolation_enabled": False,
            "double_trigger": False,
            "double_trigger_delay": 0.5,
            "mapping": {}
        })

    async def async_update_virtual_light_config(self, area_id: str, config: dict):
        """Update virtual light config for an area and save."""
        self.data["virtual_light"][area_id] = config
        await self.async_save()
