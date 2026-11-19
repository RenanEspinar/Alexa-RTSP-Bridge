"""Monitor an existing Alexa RTSP Bridge Pro gateway from Home Assistant."""
from datetime import timedelta
import asyncio
import logging

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_GATEWAY_URL, DOMAIN

PLATFORMS = [Platform.SENSOR]

class BridgeCoordinator(DataUpdateCoordinator):
    """Poll only public metadata, never camera passwords or signed media URLs."""

    def __init__(self, hass: HomeAssistant, url: str):
        super().__init__(hass, logging.getLogger(__name__),
                         name='Alexa RTSP Bridge Pro', update_interval=timedelta(seconds=15))
        self.url = url

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(8):
                async with async_get_clientsession(self.hass).get(self.url + '/api/state') as response:
                    response.raise_for_status()
                    payload = await response.json()
            if not isinstance(payload.get('cameras'), list) or not isinstance(payload.get('status'), dict):
                raise ValueError('Unexpected gateway response')
            # Do not store the gateway's CSRF token in the coordinator cache.
            return {k: payload[k] for k in ('version','cameras','status','uptime_seconds') if k in payload}
        except (TimeoutError, ClientError, ValueError, KeyError) as exc:
            raise UpdateFailed(f'Gateway unavailable: {type(exc).__name__}') from exc

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = BridgeCoordinator(hass, entry.data[CONF_GATEWAY_URL])
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
