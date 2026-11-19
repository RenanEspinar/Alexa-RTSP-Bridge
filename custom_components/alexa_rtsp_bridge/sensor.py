"""Camera count and running-stream sensors; private URLs are never exposed."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BridgeSensor(coordinator, entry, key) for key in ('cameras', 'running', 'uptime')])


class BridgeSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f'{entry.entry_id}_{key}'
        self._attr_name = {'cameras':'Configured cameras', 'running':'Active streams', 'uptime':'Gateway uptime'}[key]
        self._attr_icon = {'cameras':'mdi:cctv', 'running':'mdi:video-wireless', 'uptime':'mdi:timer-outline'}[key]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN,entry.entry_id)}, name='Alexa RTSP Bridge Pro', manufacturer='Renan Espinar', model='RTSP–HLS gateway')
        if key == 'uptime':
            self._attr_native_unit_of_measurement = 's'

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        if self.key == 'cameras':
            return len(d.get('cameras', []))
        if self.key == 'running':
            return sum(bool(x.get('running')) for x in d.get('status', {}).values() if isinstance(x, dict))
        return d.get('uptime_seconds')
