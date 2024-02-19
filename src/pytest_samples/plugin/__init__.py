"""This module contains the entrypoint and the actual plugin
implementation.
"""

__all__ = [
    "SamplesBrokerBootstrap", "CmdFlags",
    "SamplesBrokerBase", "NoStateSamplesBroker",
    "ImmediateStatefulSamplesBroker", "LazyStatefulSamplesBroker",
    "TestResultStateNotImplementedWarning",
    "pytest_load_initial_conftests"
]

import sys as _sys

from pytest import Config as _Config

from ._bootstrap import SamplesBrokerBootstrap, CmdFlags
from ._broker_base import SamplesBrokerBase
from ._broker_nostate import NoStateSamplesBroker
from ._broker_stateful import ImmediateStatefulSamplesBroker, \
    LazyStatefulSamplesBroker, TestResultStateNotImplementedWarning

from . import _meta


_this_module = _sys.modules[__name__]
"""The object representing this module "plugin" containing the initial
version of the plugin.
"""


# Registering the plugin here makes it possible to let the ini config
# file decide which broker to load. This may be useful for future
# extensions.
def pytest_load_initial_conftests(early_config: _Config) -> None:
    """Function called as part of pytest bootstrapping. Internally used
    to load conftests. Here used to install the plugin.

    Args:
        early_config (Config): The config.
        args (List[str]): The command line arguments.
        parser (Parser): The parser.

    Raises:
        RuntimeError: If the plugin could not be registered.
    """
    _meta.swap_plugin(
        early_config.pluginmanager, _this_module, SamplesBrokerBootstrap()
    )
