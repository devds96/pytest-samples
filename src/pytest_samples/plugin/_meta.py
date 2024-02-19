"""This module contains meta information and functions for the
plugin.
"""

__all__ = [
    "PLUGIN_NAME", "PLUGIN_FULL_NAME",
    "swap_plugin", "register", "unregister"
]

import logging

from pytest import PytestPluginManager as _PytestPluginManager
from typing import Optional as _Optional


_logger = logging.getLogger(__name__)
"""The logger for this module."""


PLUGIN_NAME = "samples"
"""The name of the plugin."""


PLUGIN_FULL_NAME = "pytest-samples"
"""The full name of the plugin with "pytest-" prefix."""


def swap_plugin(
    pluginmanager: _PytestPluginManager, old_value: object, new_value: object
) -> None:
    """Swap the plugin object with a new object.

    Args:
        pluginmanager (PytestPluginManager): The pytest plugin manager.
        new_value (object): The new lugin object to register.
        unreg (bool, optional): Whether to unregister the module first.
    """
    unregister(pluginmanager, old_value)
    register(pluginmanager, new_value)


def register(
    pluginmanager: _PytestPluginManager, plugin_object: object
) -> _Optional[str]:
    """Register a new plugin object under this plugin's name.

    Args:
        pluginmanager (PytestPluginManager): The pytest plugin manager.
        plugin_object (object): The plugin object to register.

    Returns:
        Optional[str]: The result of the `register` call on
            `pluginmanager`.
    """
    _logger.debug("Registering new module object %r.", plugin_object)
    res = pluginmanager.register(plugin_object, PLUGIN_NAME)
    _logger.debug("New module object registered. Result: %r.", res)
    return res


def unregister(
    pluginmanager: _PytestPluginManager, plugin_object: object
) -> _Optional[object]:
    """Unregister a plugin object.

    Args:
        pluginmanager (PytestPluginManager): The pytest plugin manager.
        plugin_object (object): The plugin object to unregister.

    Returns:
        Optional[object]: The result of the `unregister` call on
            `pluginmanager`.
    """
    _logger.debug("Unregistering module object %r.", plugin_object)
    old = pluginmanager.unregister(plugin_object)
    _logger.debug("Got %r.", old)
    return old
