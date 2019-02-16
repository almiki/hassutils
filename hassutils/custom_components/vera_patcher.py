"""
The Vera component only tries connecting to the Vera once on startup. If the Vera
hasn't booted yet (e.g. after a power outage), too bad. This component modifies the
Vera component to periodically retry the connection on failure.

This component should be declared before vera in the config yaml. E.g.:

  vera_patcher:

  vera:
    vera_controller_url: http://192.168.x.x:3480
  
"""

import logging
import homeassistant.components.vera as vera
# from homeassistant.components.vera import *
from homeassistant.helpers.event import call_later


_LOGGER = logging.getLogger(__name__)
_EVENT_LOADED = 'vera_loaded'
_EVENT_LOAD_FAILED = 'vera_load_failed'
DOMAIN = "vera_patcher"


def _patch():
    _LOGGER.info("Patching Vera setup")

    def setup(hass, base_config):
        """
        This is mostly copied from homeassistant.components.vera.setup(), with modifications to
        support retries.
        """

        DOMAIN = vera.DOMAIN

        import pyvera as veraApi
        _LOGGER.info("Running patched Vera setup")

        def stop_subscription(event):
            """Shutdown Vera subscriptions and subscription thread on exit."""
            _LOGGER.info("Shutting down subscriptions")
            hass.data[vera.VERA_CONTROLLER].stop()

        config = base_config.get(DOMAIN)

        # Get Vera specific configuration.
        base_url = config.get(vera.CONF_CONTROLLER)
        light_ids = config.get(vera.CONF_LIGHTS)
        exclude_ids = config.get(vera.CONF_EXCLUDE)

        # Initialize the Vera controller.
        controller = hass.data[vera.VERA_CONTROLLER] = veraApi.init_controller(base_url)[0]
        hass.bus.listen_once(vera.EVENT_HOMEASSISTANT_STOP, stop_subscription)

        def checker(controller, next_check=30, is_retry=False):
            _LOGGER.info("Connecting to Vera")

            vera_devices = vera.defaultdict(list)
            vera_scenes = []

            try:
                devices = controller.get_devices()
                scenes = controller.get_scenes()

            except vera.RequestException:
                # There was a network related error connecting to the Vera controller.
                next_delay = min(3600, round(next_check * 3 // 2))
                _LOGGER.exception("Error communicating with Vera API, retrying in {}s".format(next_delay))

                def handler(*_):
                    hass.data[vera.VERA_CONTROLLER].stop()
                    controller = hass.data[vera.VERA_CONTROLLER] = veraApi.init_controller(base_url)[0]

                    # On subsequent checks, do the requests on a worker thread since it blocks for a while.
                    hass.add_job(lambda: checker(controller, next_delay, True))

                call_later(hass, next_check, handler)
                hass.bus.fire(_EVENT_LOAD_FAILED, {})
                return False

            for device in devices:
                if device.device_id in exclude_ids:
                    continue

                device_type = vera.map_vera_device(device, light_ids)
                if not device_type:
                    continue

                vera_devices[device_type].append(device)

            vera_scenes.extend(scenes)

            def load(*_):
                hass.data[vera.VERA_DEVICES] = vera_devices
                hass.data[vera.VERA_SCENES] = vera_scenes

                if is_retry:
                    for component in vera.VERA_COMPONENTS:
                        vera.discovery.load_platform(hass, component, DOMAIN, {}, base_config)

                hass.bus.fire(_EVENT_LOADED, {})

            if not is_retry:
                load()

            else:
                call_later(hass, 0, load)

            return True


        hass.data[vera.VERA_DEVICES] = vera.defaultdict(list)
        hass.data[vera.VERA_SCENES] = []

        checker(controller)

        # Initially call load_platform() even if Vera connection failed, just to get
        # the platforms loaded. We'll call them again if we succeed on a retry.
        for component in vera.VERA_COMPONENTS:
            vera.discovery.load_platform(hass, component, DOMAIN, {}, base_config)

        return True

    vera.setup = setup

_patch()


def setup(hass, base_config):
    # This component does nothing aside from patching vera.setup().
    return True
