"""Initial setup form shown under Settings > Devices & Services."""
from __future__ import annotations
import asyncio
from urllib.parse import urlsplit

from aiohttp import ClientError
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_GATEWAY_URL, DOMAIN


def normalize_gateway_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Gateway URL must be text')
    v = value.strip().rstrip('/')
    u = urlsplit(v)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError('Enter a base HTTP(S) URL without credentials, path or query')
    return v


class AlexaRtspBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                gateway_url = normalize_gateway_url(user_input[CONF_GATEWAY_URL])
            except (ValueError, KeyError):
                errors['base'] = 'invalid_url'
            else:
                try:
                    async with asyncio.timeout(8):
                        async with async_get_clientsession(self.hass).get(gateway_url + '/api/state') as response:
                            response.raise_for_status()
                            payload = await response.json()
                    if not isinstance(payload.get('cameras'), list) or not isinstance(payload.get('status'), dict):
                        errors['base'] = 'not_bridge'
                    else:
                        await self.async_set_unique_id(gateway_url)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(title='Alexa RTSP Bridge Pro', data={CONF_GATEWAY_URL: gateway_url})
                except (TimeoutError, ClientError, ValueError):
                    errors['base'] = 'cannot_connect'
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({vol.Required(CONF_GATEWAY_URL, default='http://127.0.0.1:18099'): str}),
            errors=errors,
        )
