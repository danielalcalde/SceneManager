"""The Scene Manager integration."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.helpers import discovery

from .const import DOMAIN
from .store import SceneManagerStore
from .services import async_setup_services
from .api import async_setup_api

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Scene Manager component."""
    _LOGGER.info("Setting up Scene Manager")
    hass.data.setdefault(DOMAIN, {})

    # Initialize and load storage
    store = SceneManagerStore(hass)
    await store.async_load()
    hass.data[DOMAIN]["store"] = store

    # Set up services
    await async_setup_services(hass, store)
    
    # Set up WebSocket API for the frontend
    async_setup_api(hass)
    
    # Register Sidebar Panel (Expects the JS to be in <config>/www/scene_manager/)
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Scene Manager",
        sidebar_icon="mdi:palette-swatch",
        frontend_url_path="scene_manager",
        require_admin=True,
        config={
            "_panel_custom": {
                "name": "scene-manager-panel",
                "module_url": "/local/scene_manager/scene-manager-panel.js"
            }
        }
    )
    
    # Load switch platform to generate virtual entities
    hass.async_create_task(
        discovery.async_load_platform(
            hass, "switch", DOMAIN, {}, config
        )
    )
    
    # Load light platform to generate virtual entities
    hass.async_create_task(
        discovery.async_load_platform(
            hass, "light", DOMAIN, {}, config
        )
    )

    return True
