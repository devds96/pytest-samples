import argparse as _argparse
import os.path as _ospath
import pytest as _pytest
import pytimeparse as _pytimeparse

from datetime import timedelta as _timedelta
from pytest import Config as _Config, Parser as _Parser
from typing import NoReturn as _NoReturn, Optional as _Optional, \
    Type as _Type

from ._broker_stateful import StatefulSamplesBroker as _StatefulSamplesBroker
from . import _broker_nostate
from . import _broker_stateful
from . import _meta


class CmdFlags:
    """Contains the command line flags."""

    mode = f"--{_meta.PLUGIN_NAME}"
    """The flag to enable and set the mode of operation of the
    plugin.
    """

    db_path = f"--{_meta.PLUGIN_NAME}-db-path"
    """The flag for the state database path."""

    soft_timeout = f"--{_meta.PLUGIN_NAME}-soft-timeout"
    """The flag for the soft timeout time."""

    hash_testfiles = f"--{_meta.PLUGIN_NAME}-hash-testfiles"
    """The flag for whether to hash test files."""

    seed = f"--{_meta.PLUGIN_NAME}-seed"
    """The flag for the seed."""

    write_immediately = f"--{_meta.PLUGIN_NAME}-write-immediately"
    """The flag for the option to write the state immediately."""

    randomize = f"--{_meta.PLUGIN_NAME}-randomize"
    """The flag for a randomized test order in state mode."""

    no_pruning = f"--{_meta.PLUGIN_NAME}-no-pruning"
    """The flag for keeping no longer existent tests in the database."""

    nostate_seeded = f"--{_meta.PLUGIN_NAME}-nostate-seeded"
    """The flag for keeping no longer existent tests in the database."""

    reset_on_saturation = f"--{_meta.PLUGIN_NAME}-reset-on-saturation"
    """The flag to enable a reset after all tests have been stored in
    the database and therefore passed at least once.
    """

    overwrite_broken_db = f"--{_meta.PLUGIN_NAME}-overwrite-broken-db"
    """Flag used to enable overwriting broken database files in
    stateful mode.
    """

    enable_db_logging = f"--{_meta.PLUGIN_NAME}-enable-db-logging"
    """Flag to enable logging of the underlying database engine/
    implementation.
    """


class _ModeKeys:
    """Contains the keys (names) of the modes of operations for the
    plugin.
    """

    nostate = "nostate"
    """The mode in which no state information regarding the tests is
    recorded.
    """

    stateful = "stateful"
    """The mode in which information regarding the tests is recorded in
    a database.
    """


class ConfigWarning(UserWarning):
    """A warning that is issued in connection with config issues."""
    pass


class SeedSetInNoStateMode(ConfigWarning):
    """A warning that is issued if a seed value is provided in "no
    state" mode.
    """
    pass


class SamplesBrokerBootstrap:

    @classmethod
    def _parse_soft_timeout(  # pragma: no cover
        cls, value: str
    ) -> _Optional[_timedelta]:
        """Parses the soft timeout value provided to the command line.

        Args:
            value (str): The provided value.

        Raises:
            ArgumentTypeError: If a valid `timedelta` could not be
                created due to a malformed string.

        Returns:
            Optional[timedelta]: The created `timedelta` instance or
                None, if the time should be infinite.
        """
        if value == "off":
            return None
        seconds = _pytimeparse.parse(value)
        if seconds is None:
            raise _argparse.ArgumentTypeError(
                f"Could not parse a valid time delta from {value!r}."
            )
        return _timedelta(seconds=seconds)

    def pytest_addoption(self, parser: _Parser) -> None:
        """The function called for the pytest "addoption" hook to add
        options for this plugin.

        Args:
            parser (Parser): The parser.
            pluginmanager (PytestPluginManager): The plugin manager.
        """
        pname = _meta.PLUGIN_NAME
        g = parser.getgroup(
            f"--{pname}", _meta.PLUGIN_FULL_NAME
        )
        g.addoption(
            CmdFlags.mode,
            help=(
                "Enable the samples plugin to only test some tests "
                "(samples). If not enabled, all other flags of this "
                "plugin will be ignored (not checked). The provided "
                "argument will determine the mode of operation for the "
                "plugin. In \"nostate\" mode, the tests will simply be "
                "shuffled to allow different tests to run first with "
                "each run. In \"stateful\" mode a database path must "
                f"be provided with {CmdFlags.db_path}. A database "
                "containing information about the last passed tests "
                "will be saved to this path to allow failed and "
                "never run tests to be run before passed tests."
            ),
            choices=(_ModeKeys.nostate, _ModeKeys.stateful)
        )
        g.addoption(
            CmdFlags.db_path,
            help=(
                "Path to the database file in which to store the "
                "information regarding tests that have been run. This "
                "file will be modified. If the file does not exist, it "
                "will be created. This argument must not be set in nostate "
                "mode. Relative paths will be interpreted with respect "
                "to the current working directory."
                f"{CmdFlags.mode}={_ModeKeys.nostate}."
            ),
            metavar="db_path"
        )
        g.addoption(
            CmdFlags.soft_timeout,
            help=(
                "Set the soft timeout time. Once it expires, all remaining "
                "tests will be marked as \"skipped\". Whether the timeout "
                "has expired is only checked after each test, meaning "
                "that running tests will not be stopped by the timeout. "
                "Defaults to 50 minutes. Supports all formats defined "
                "by the pytimeparse package. Can be set to \"off\" to "
                "deactivate the soft timeout."
            ),
            default=_timedelta(minutes=50),
            metavar="soft_timeout",
            type=self._parse_soft_timeout
        )
        g.addoption(
            CmdFlags.hash_testfiles,
            help=(
                "Use hashes of the files containing the tests in an "
                "attempt to detect changes. This does not guarantee a"
                "perfect detection of changes, for example when fixtures "
                "defined externally change or when hash collisions "
                "occur."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.seed,
            help=(
                "The seed to be used for random numbers. If this is set "
                "in \"nostate\" mode a warning will be emitted, unless "
                f"{CmdFlags.nostate_seeded} is set because each test run "
                "would be identical. The provided value will be passed "
                "directly as a string to the python RNG."
            ),
            default=None,
            metavar="seed",
            type=str
        )
        g.addoption(
            CmdFlags.write_immediately,
            help=(
                "If this flag is set, the database will be updated after "
                "every successful test. Otherwise, it will only be updated "
                "after all tests are finished (or have been skipped). "
                "This flag is ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.randomize,
            help=(
                "If this flag is set, the tests which have not yet been "
                "run before will be run in a randomized order. This flag "
                "will be ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.no_pruning,
            help=(
                "If this flag is set, tests that are no longer found "
                "will not be removed from the database. This flag will "
                "be ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.nostate_seeded,
            help=(
                "Suppress the warning regarding fixed seeds in "
                "\"nostate\" mode. This flag will be ignored in "
                "\"stateful\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.reset_on_saturation,
            help=(
                "Drop all entries from the database once all tests are "
                "stored in it and therefore have passed at least once. "
                "This is especially useful in combination with "
                f"{CmdFlags.randomize} with a random seed. If all tests "
                "pass, the database will also be left empty. This flag will "
                "be ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.overwrite_broken_db,
            help=(
                "Overwrite broken database files in stateful mode. "
                "WARNING: This may delete the database file and can lead to "
                "DATA LOSS! This flag will be ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )
        g.addoption(
            CmdFlags.enable_db_logging,
            help=(
                "Enable database related logging such as logging of SQL "
                "statements. This flag will be ignored in \"nostate\" mode."
            ),
            action="store_true",
            default=False
        )

    def _cmdline_error(self, message: str) -> _NoReturn:  # pragma: no cover
        """Print the command line error message from the command line
        parser.

        Args:
            config (Config): The config.
            message (str): The error message.

        Raises:
            RuntimeError: If exiting via the argument parser failed, for
                example, if the instance could not be obtained.
        """
        raise _pytest.UsageError(message)

    def pytest_configure(self, config: _Config) -> None:
        """The pytest hook called to configure the plugin.

        Args:
            config (Config): The config.
        """
        pluginmanager = config.pluginmanager
        _meta.unregister(pluginmanager, self)

        mode = config.getoption(CmdFlags.mode)
        if mode is None:
            # Not enabled, since no mode was provided.
            return

        db_path: _Optional[str] = config.getoption(CmdFlags.db_path)

        soft_timeout = config.getoption(CmdFlags.soft_timeout)
        seed = config.getoption(CmdFlags.seed)

        if mode == _ModeKeys.nostate:
            if db_path is not None:
                self._cmdline_error(  # pragma: no cover
                    "The mode was set to "
                    f"{CmdFlags.mode}={_ModeKeys.nostate}, but"
                    f"{CmdFlags.db_path} was provided."
                )
            if seed is not None:
                is_ok = config.getoption(CmdFlags.nostate_seeded)
                if not is_ok:
                    warning = SeedSetInNoStateMode(
                        "A seed value was provided in \"no state\" mode. "
                        "This is only recommended when testing the plugin "
                        "itself since each test iteration will be "
                        "identical if the and some tests may not get run. "
                        "If you know what you are doing, additionally "
                        f"pass the {CmdFlags.nostate_seeded} flag to "
                        "suppress this warning."
                    )
                    config.issue_config_time_warning(warning, 2)
            p = _broker_nostate.NoStateSamplesBroker(soft_timeout, seed)
            _meta.register(pluginmanager, p)
            return

        if mode != _ModeKeys.stateful:
            raise AssertionError(
                f"An invalid mode key was provided: {mode!r}"
            )
        if db_path is None:
            self._cmdline_error(  # pragma: no cover
                "The mode was set to "
                f"{CmdFlags.mode}={_ModeKeys.stateful}, but "
                "no database path was provided via "
                f"{CmdFlags.db_path}."
            )

        db_path = _ospath.realpath(db_path)
        hash_testfiles = config.getoption(CmdFlags.hash_testfiles)
        randomize = config.getoption(CmdFlags.randomize)
        no_pruning = config.getoption(CmdFlags.no_pruning)
        reset_on_saturation = config.getoption(CmdFlags.reset_on_saturation)
        overwrite_broken_db = config.getoption(CmdFlags.overwrite_broken_db)
        enable_db_logging = config.getoption(CmdFlags.enable_db_logging)
        write_immediately = config.getoption(CmdFlags.write_immediately)

        rootpath = str(config.rootpath)

        if enable_db_logging:  # pragma: no branch
            # We make this import here because the plugin might not
            # actually get enabled. But once we are here, a database
            # connection will be inevitable and we can enable logging.
            from ..database import enable_logging
            enable_logging()

        plugin_cls: _Type[_StatefulSamplesBroker]
        if write_immediately:
            plugin_cls = _broker_stateful.ImmediateStatefulSamplesBroker
        else:
            plugin_cls = _broker_stateful.LazyStatefulSamplesBroker

        plugin = plugin_cls(
            rootpath,
            soft_timeout,
            seed,
            db_path,
            hash_testfiles,
            randomize,
            no_pruning,
            reset_on_saturation,
            overwrite_broken_db
        )

        _meta.register(pluginmanager, plugin)
