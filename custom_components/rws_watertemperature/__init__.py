"""The Rijkswaterstaat water temperature integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RwsClient
from .const import DOMAIN, LAST_MEASUREMENT_KEY
from .coordinator import RwsConfigEntry, RwsCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: RwsConfigEntry) -> bool:
    """Set up Rijkswaterstaat water temperature from a config entry."""
    coordinator = RwsCoordinator(hass, entry, RwsClient(async_get_clientsession(hass)))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_remove_deselected(hass, entry, coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _async_remove_deselected(
    hass: HomeAssistant, entry: RwsConfigEntry, coordinator: RwsCoordinator
) -> None:
    """Remove devices and entities for locations or quantities no longer selected."""
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not any(
            domain == DOMAIN and code in coordinator.codes
            for domain, code in device.identifiers
        ):
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )

    expected = {
        f"{code}_{key}"
        for code in coordinator.codes
        for key in (*coordinator.quantities, LAST_MEASUREMENT_KEY)
    }
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.unique_id not in expected:
            entity_registry.async_remove(entity.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: RwsConfigEntry) -> None:
    """Reload the entry when the selection of locations or quantities changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RwsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
