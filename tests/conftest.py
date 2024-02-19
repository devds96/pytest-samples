import collections as _collections
import functools as _functools
import hypothesis.strategies as _strategies
import hypothesis_fspaths as _hypothesis_fspaths
import itertools as _itertools
import logging as _logging
import os as _os
import os.path as _ospath
import pytest as _pytest
import shlex as _shlex
import shutil as _shutil
import sqlalchemy as _sqlalchemy
import sqlalchemy.orm as _orm
import tempfile as _tempfile

from arrow import Arrow as _Arrow
from contextlib import AbstractContextManager as _AbstractContextManager, \
    contextmanager as _contextmanager
from dataclasses import dataclass as _dataclass
from hypothesis.strategies import composite as _composite, \
    DrawFn as _DrawFn, SearchStrategy as _SearchStrategy
from pytest import fixture as _fixture, Pytester as _Pytester, \
    RunResult as _RunResult
from pytest_mock import MockerFixture as _MockerFixture
from tempfile import TemporaryDirectory as _TemporaryDirectory
from types import TracebackType as _TracebackType
from typing import Any as _Any, DefaultDict as _DefaultDict, \
    Dict as _Dict, Iterable as _Iterable, Optional as _Optional, \
    Sequence as _Sequence, Tuple as _Tuple, Type as _Type, \
    Union as _Union

import pytest_samples.plugin as _plugin

from pytest_samples.database import EngineBase as _EngineBase, \
    Engine as _Engine, TestFile as _TestFile, TestItem as _TestItem
from pytest_samples.tools import copy_fileobj_to_func
from pytest_samples.types import Location as _Location


_logger = _logging.getLogger(__name__)
"""The logger for this module."""


def optional_binary() -> _SearchStrategy[_Union[bytes, None]]:
    """Get a hypothesis strategy to generate `bytes` or None."""
    return _strategies.one_of(_strategies.binary(), _strategies.none())


def optional_integers() -> _SearchStrategy[_Union[int, None]]:
    """Get a hypothesis strategy to generate `int`s or None."""
    return _strategies.one_of(_strategies.integers(), _strategies.none())


def str_paths() -> _SearchStrategy[str]:
    """A hypothesis strategy for generating `str` paths."""
    return _hypothesis_fspaths.fspaths(False).filter(
        lambda p: isinstance(p, str)
    )


@_composite
def locations(draw: _DrawFn) -> _Location:
    """A hypothesis strategy generating `Location`s."""
    path = draw(str_paths())
    lineno = draw(optional_integers())
    testname = draw(_strategies.text())
    return (path, lineno, testname)


@_composite
def testfiles(draw: _DrawFn) -> _TestFile:
    """A hypothesis strategy generating `TestFile` instances."""
    return _TestFile(
        id=draw(_strategies.integers()),
        path=draw(_strategies.text()),
        last_hash=draw(optional_binary())
    )

# Prevent pytest from collecting the strategy
testfiles.__test__ = False  # type: ignore [attr-defined] # noqa: E305


def rel_str_paths() -> _SearchStrategy[str]:
    """A hypothesis strategy to generate relative str paths of nonzero
    length.
    """
    return str_paths().filter(
        lambda p: (not _ospath.isabs(p)) and len(p) > 0
    )


def run_pytest(pytester: _Pytester, timeout: str, *args: str) -> _RunResult:
    """Run pytest to test the plugin.

    Args:
        pytester (Pytester): The `Pytester` instance to use for the
            test.
        *args (str): The arguments.

    Returns:
        RunResult: The produced result.
    """
    return pytester.runpytest(
        "-o", "python_files=itest_*.py",
        "--full-trace",
        "--log-cli-level=debug",
        "--tb=no",
        _plugin.CmdFlags.enable_db_logging,
        f"{_plugin.CmdFlags.soft_timeout}={timeout}",
        *args
    )


class InMemoryEngine(_EngineBase):
    """An in-memory version of the engine used for testing."""

    def __init__(self) -> None:
        """Initialize a new in-memory engine object."""
        engine = _sqlalchemy.create_engine("sqlite://")
        super().__init__(engine)

    def get_underlying_engine(self) -> _sqlalchemy.Engine:
        """Obtain the underlying engine. This function should only be
        called by test functions.

        Returns:
            sqlalchemy.Engine: The underlying sqlalchemy engine.
        """
        return self._engine


@_fixture(scope="function")
def populated_engine() -> InMemoryEngine:
    """Fixture to construct a populate in-memory database."""
    engine = InMemoryEngine()
    engine.setup_tables()
    with engine.new_session() as s:
        f1 = s.add_file("abc", b"123")
        f2 = s.add_file("def", b"456")
        s.add_file("ghi", None)

        s.add_or_update_item(f1, 0, "t1", _Arrow.utcnow())
        s.add_or_update_item(f1, 1, "t2", _Arrow.utcnow())
        s.add_or_update_item(f1, 2, "t3", _Arrow.utcnow())
        s.add_or_update_item(f1, 3, "t4", _Arrow.utcnow())

        # t5 located in the past
        s.add_or_update_item(f2, 0, "t5", _Arrow.utcnow())
        s.add_or_update_item(f2, 1, "t6", _Arrow.utcnow())

    return engine


INVALID_DATABASE_PATH = _os.devnull
"""Invalid path used for tests."""


@_dataclass(frozen=True)
class DatabaseMocked:

    __slots__ = (
        "database_path",
        "args",
        "engine",
        "_os_truncate"
    )

    database_path: str
    """The path to the database file."""

    args: _Iterable[str]
    """The arguments to pass to the command line."""

    engine: InMemoryEngine
    """The database engine."""

    _os_truncate: _Any
    """The mocked value of `os_truncate`."""

    def __init__(self, database_path: str, engine: InMemoryEngine) -> None:
        """Initialize the `DatabaseCollector`.

        Args:
            database_path (str): The database path.
        """
        object.__setattr__(self, "database_path", database_path)
        escaped_path = _shlex.quote(database_path)
        args = (f"{_plugin.CmdFlags.db_path}={escaped_path}",)
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "engine", engine)
        object.__setattr__(self, "_os_truncate", _os.truncate)

    def assert_no_truncate_call(self):
        """Assert that `os.truncate` has not been called."""
        assert not self._os_truncate.called


@_fixture(scope="function")
def database_mocked(mocker: _MockerFixture):
    """A fixture generating a `DatabaseCollector`."""

    ime = InMemoryEngine()

    class MockEngineClass(_Engine):
        """A class to mock the `_Engine` and instead create an in-memory
        engine.
        """

        def __init__(self, p: str) -> None:
            """Construct the engine.

            Args:
                p (str): The path is ignored and only stored in the
                    `_path` slot.
            """
            self._path = p
            self._engine = ime.get_underlying_engine()
            # This must be set because the Engine class accesses the
            # field.
            self._disposed = False

        # This will shadow the dispose function which would destroy the
        # database.
        def dispose(self) -> None:
            """Does not perform any action."""
            pass

    mocker.patch("pytest_samples.database.Engine", MockEngineClass)
    mocker.patch("os.truncate")

    yield DatabaseMocked(INVALID_DATABASE_PATH, ime)

    # This will call EngineBase.dispose, which is not mocked.
    ime.dispose()


@_dataclass(frozen=True)
class OnDiskDatabase(_AbstractContextManager):
    """Encapsulates information regarding an on-disk database."""

    __slots__ = ("tempdir", "engine", "tempfile", "args")

    tempdir: str
    """The temporary directory where the database is located."""

    engine: _Engine
    """The engine."""

    tempfile: str
    """The path to the temporary file representing the database."""

    args: _Iterable[str]
    """The args to pass to the pytetst call to access the database."""

    def __init__(self, tempdir: str) -> None:
        """Initizalize the `OnDiskDatabase`."""
        # mktemp should be fine since we own the directory.
        object.__setattr__(self, "tempdir", tempdir)
        file = _tempfile.mktemp(dir=tempdir, suffix=".sqlite")
        object.__setattr__(self, "tempfile", file)
        engine = _Engine(file)
        object.__setattr__(self, "engine", engine)
        args = (f"{_plugin.CmdFlags.db_path}={file}",)
        object.__setattr__(self, "args", args)

    def __enter__(self):
        """Enter the context.

        Returns:
            OnDiskDatabase: self.
        """
        return self

    def __exit__(
        self,
        exc_type: _Optional[_Type[BaseException]],
        exc_value: _Optional[BaseException],
        traceback: _Optional[_TracebackType]
    ) -> None:
        """Dispose the underlying engine.

        Args:
            exc_type (Optional[Type[BaseException]]): Type of a possible
                exception in the contex.
            exc_value (Optional[BaseException]): Value of a possible
                exception in the context.
            traceback (Optional[TracebackType]): The possible traceback.
        """
        self.engine.dispose()

    def _replace_zeros(self, size: int) -> None:
        """Truncate the file and fill it with '\\0' characters.

        Args:
            size (int): The number of null bytes to write.
        """
        db_file = self.tempfile
        with open(db_file, "w+b") as ofi:
            ofi.write(b'\0' * size)

    def destroy_file(self, minsize: int) -> None:
        """Destroy the file, leaving it at the same size, but filled
        with '\\0' characters.
        """
        try:
            size = _ospath.getsize(self.tempfile)
        except FileNotFoundError:
            size = minsize
        else:
            size = min(size, minsize)
        self._replace_zeros(size)

    def assert_all_zeros(self, n: int) -> None:
        """Check that the database file only contains '\\0' characters.

        Args:
            n (int): The number of '\\0' characters to assert.
        """

        num = 0

        def write(b: bytes):
            nonlocal num
            num += len(b)
            assert sum(b) == 0

        with open(self.tempfile, "rb") as ifi:
            copy_fileobj_to_func(ifi, write)

        assert num == n


@_fixture(scope="function")
def ondisk_database(tempdir_base: _Optional[str] = None):
    """A fixture holding an on-disk database."""
    with _TemporaryDirectory(dir=tempdir_base) as tdir:
        with OnDiskDatabase(tdir) as odd:
            yield odd


_ResultsDict = _Dict[str, _Tuple[str, int]]
"""A dictionary containin information regarding the results of tests."""


def expect_written(state: str) -> bool:
    """Check whether a tests with a given result state should be
    expected to have been written to the database.

    Args:
        state (str): The result state of the test.

    Returns:
        bool: Whether the test should be expected in the database.
    """
    return state in ("passed", "xfailed", "xpassed")


def assert_database_entries(  # noqa: C901
    database: _Union[InMemoryEngine, OnDiskDatabase],
    expected_files: _Dict[str, _ResultsDict],
    *,
    remove_empty_files: _Optional[bool] = None
) -> None:
    """Assert that the database has a certain set of entries.

    Args:
        engine (EngineBase): The engine to inspect the database.
        expected_files (Dict[str, ResultsDict]): A dictionary mapping
            the names of expected files to the items (failed or passed)
            associated with that file
        remove_empty_files (bool, optional): Whether to remove empty
            files before comparing the structure to the database.
            Defaults to False.
    """
    if remove_empty_files is None:
        remove_empty_files = False

    engine: _EngineBase
    if isinstance(database, InMemoryEngine):
        inner = database.get_underlying_engine()
        make_session = _functools.partial(_orm.Session, inner)
        engine = database
    elif isinstance(database, OnDiskDatabase):
        engine = database.engine

        @_contextmanager
        def make_session():
            """Opens an `sqlalchemy.orm.Session`."""
            try:
                engine = _Engine.create_engine(database.tempfile)
                with _orm.Session(engine) as session:
                    yield session
            finally:
                engine.dispose()

    else:
        raise TypeError(f"'database' was {database!r}.")

    def filter_written(rd: _ResultsDict) -> _Dict[str, int]:
        return {k: v[1] for k, v in rd.items() if expect_written(v[0])}

    filtered = {fn: filter_written(rd) for fn, rd in expected_files.items()}

    if remove_empty_files:
        filtered = {fn: rd for fn, rd in filtered.items() if (len(rd) > 0)}

    num_exp_files = len(filtered)
    num_exp_items = sum(map(len, filtered.values()))

    with make_session() as session:
        tfis = session.query(_TestFile).all()
        _logger.debug("All 'TestFile's: %r", tfis)
        assert len(tfis) == num_exp_files

        items = session.query(_TestItem).all()
        _logger.debug("All 'TestItem's: %r", items)
        assert len(items) == num_exp_items

        path_map: _Dict[str, str] = dict()

        # If we run tests with tox, the paths stored in the database are
        # relative to the base dir of "".tox". We therefore have to
        # extract the base names first. The file names themself will be
        # unique.
        for file in tfis:
            path = file.path
            key = _ospath.basename(path)
            _logger.debug("Mapping: %r -> %r", key, path)
            path_map[key] = path

    with engine.new_session() as s:
        for filename, results in filtered.items():
            db_filename = path_map[filename]
            file = s.try_get_file(db_filename)
            assert file is not None, filename
            for testname, lineno in results.items():
                ti = s.try_get_item(file, lineno, testname)
                assert ti is not None, (lineno, testname)


class ExamplesFile1:
    """Contains information regarding the examples file 1."""

    FILENAME = "itest_examples_1.py"
    """The file name of the exmaples file 1."""

    RESULTS: _ResultsDict = {
        "test_dummy1": ("passed", 5),
        "test_dummy2": ("passed", 9),
        "test_dummy3": ("passed", 13),
        "test_dummyp[0]": ("passed", 17),
        "test_dummyp[1]": ("passed", 17),
        "test_dummyp[2]": ("passed", 17),
        "TestClass.test_dummyc": ("passed", 24),
        "test_xfail": ("xfailed", 28),
        "test_xpass": ("xpassed", 33),
        "test_fail": ("failed", 38),
        "test_error": ("failed", 42)
    }
    """Contains the results and line numbers for the tests of examples
    file 1. The results are on order of appearance of the test in the
    file.
    """

    NUM_ITEMS = len(RESULTS)
    """The number of test items in the file."""

    TWO_PASSING_ITEMS = dict(_itertools.islice(
        filter(lambda x: x[1][0] == "passed", RESULTS.items()),
        2
    ))
    """Contains two passing test items."""

    @staticmethod
    def assert_result(
        result: _RunResult, *, warnings: _Optional[int] = None
    ) -> None:
        """Check the result of the pytest run.

        Args:
            result (RunResult): The result to check.
            warnings (Optional[int]): The number of expected warnings.
        """
        assert result.ret == _pytest.ExitCode.TESTS_FAILED
        result.assert_outcomes(
            passed=7,
            xfailed=1,
            failed=2,
            xpassed=1,
            warnings=warnings
        )

    @classmethod
    def assert_outcome_some(
        cls,
        tests: _Sequence[str],
        run_result: _RunResult
    ):
        """Assert the outcome for a some tests that have been run, while
        the others were skipped.

        Args:
            tests (Iterable[str]): The name of the tests that ran.
            run_result (RunResult): The result of the run.
        """
        kwargs: _DefaultDict[str, int] = _collections.defaultdict(lambda: 0)
        for name in tests:
            expected_result, _ = cls.RESULTS[name]
            kwargs[expected_result] += 1
        skipped = cls.NUM_ITEMS - len(tests)
        run_result.assert_outcomes(skipped=skipped, **kwargs)


class ExamplesFile1b:
    """Contains information regarding the examples file 1b."""

    FILENAME = "itest_examples_1b.py"
    """The file name of the exmaples file 1b."""

    RESULTS: _Dict[str, _Tuple[str, int]] = {
        "test_dummy1": ("failed", 5),
        "test_dummy2_othername": ("failed", 9),
        "test_dummy3_othername": ("passed", 13),
        "test_dummyp[-1]": ("passed", 17),
        "test_dummyp[1]": ("failed", 17),
        "test_dummyp[2]": ("passed", 17),
        "test_dummyp[3]": ("passed", 17),
        "TestClass.test_dummyc": ("passed", 24),
        "test_xfail": ("xpassed", 28),
        "test_xpass": ("xfailed", 33),
        "test_fail": ("passed", 38)
    }
    """Contains the results and line numbers for the tests of examples
    file 1b.
    """

    @staticmethod
    def assert_result(
        result: _RunResult, *, warnings: _Optional[int] = None
    ) -> None:
        """Check the result of the pytest run.

        Args:
            result (RunResult): The result to check.
            warnings (Optional[int]): The number of expected warnings.
        """
        assert result.ret == _pytest.ExitCode.TESTS_FAILED
        result.assert_outcomes(
            failed=3,
            passed=6,
            xfailed=1,
            xpassed=1,
            warnings=warnings
        )


class ExamplesFile2:
    """Contains information regarding the examples file 2."""

    FILENAME = "itest_examples_2.py"
    """The file name of the exmaples file 2."""

    RESULTS: _Dict[str, _Tuple[str, int]] = {
        "test_dummy1_2": ("passed", 5),
        "test_dummyp_2[0]": ("passed", 9),
        "test_dummyp_2[1]": ("passed", 9),
        "TestClass_2.test_dummyc_2": ("xpassed", 17),
        "test_xfail_2": ("xfailed", 21)
    }
    """Contains the results and line numbers for the tests of examples
    file 2.
    """

    NUM_ITEMS = len(RESULTS)
    """The number of test items in the file."""

    @staticmethod
    def assert_MD5_hash(hash: bytes):
        """Assert that the provided MD5 hash for this file matches the
        expected value.

        Args:
            hash (bytes): The hash to check.
        """
        assert hash in (
            # "\r\n" line endings
            b"\xf9\xb8\xd6\xa2\x96\xbdP\\\xb8\x0cR\x1e\x826\x8aG",
            # "\n" line endings
            b"\x85-\x9eL\xd6\xa3\x15U\\=\x14[\xcd\n\x0c\x1b"
        )

    @staticmethod
    def assert_result(
        result: _RunResult, *, warnings: _Optional[int] = None
    ) -> None:
        """Check the result of the pytest run.

        Args:
            result (RunResult): The result to check.
            warnings (Optional[int]): The number of expected warnings.
        """
        assert result.ret == _pytest.ExitCode.OK
        result.assert_outcomes(
            passed=3,
            xfailed=1,
            failed=0,
            xpassed=1,
            warnings=warnings
        )


class ExamplesFile1b2:

    REMAINDERS: _Dict[str, _Tuple[str, int]] = {
        "test_dummy2": ("passed", 9),
        "test_dummy3": ("passed", 13),
        "test_dummyp[0]": ("passed", 17)
    }
    """Remainder elements if examples file 1 is replaced with 1b without
    elements being removed.
    """


class ExamplesFile3:
    """Contains information regarding the examples file 3."""

    FILENAME = "itest_examples_3.py"
    """The file name of the exmaples file 3."""

    NUM_ITEMS = 0
    """The number of test items in the file."""


class ExamplesFiles123:
    """Contains information regarding combined tests of the examples
    files 1-3.
    """

    FILENAMES = (
        ExamplesFile1.FILENAME,
        ExamplesFile2.FILENAME,
        ExamplesFile3.FILENAME
    )
    """The filenames of the three examples files."""

    # The third file is empty and will not be added under any
    # circumstances
    FULL_RESULT: _Dict[str, _ResultsDict] = {
        ExamplesFile1.FILENAME: ExamplesFile1.RESULTS,
        ExamplesFile2.FILENAME: ExamplesFile2.RESULTS
    }

    NUM_ITEMS = (
        ExamplesFile1.NUM_ITEMS
        + ExamplesFile2.NUM_ITEMS
        + ExamplesFile3.NUM_ITEMS
    )
    """The number of test items in the file."""

    @staticmethod
    def assert_result(
        result: _RunResult, *, warnings: _Optional[int] = None
    ) -> None:
        """Check the result of the pytest run.

        Args:
            result (RunResult): The result to check.
            warnings (Optional[int]): The number of expected warnings.
        """
        assert result.ret == _pytest.ExitCode.TESTS_FAILED
        result.assert_outcomes(
            passed=(7 + 3),
            xfailed=(1 + 1),
            failed=2,
            xpassed=(1 + 1),
            warnings=warnings
        )


class ExamplesFile4:
    """Contains information regarding the examples file 4."""

    FILENAME = "itest_examples_4.py"
    """The file name of the exmaples file 4."""

    RESULTS: _Dict[str, _Tuple[str, int]] = {
        "test_4_1": ("passed", 31),
        "test_4_2": ("passed", 35),
        "test_4_3": ("error", 39),
        "test_4_4": ("error", 43),
        "test_4_5": ("error", 47),
        "test_4_6": ("error", 51)
    }
    """Contains the results and line numbers for the tests of examples
    file 4.
    """

    NUM_ITEMS = 6
    """The number of test items in the file."""

    @staticmethod
    def assert_result(
        result: _RunResult, *, warnings: _Optional[int] = None
    ) -> None:
        """Check the result of the pytest run.

        Args:
            result (RunResult): The result to check.
            warnings (Optional[int]): The number of expected warnings.
        """
        assert result.ret == _pytest.ExitCode.TESTS_FAILED
        result.assert_outcomes(
            passed=3,
            errors=4,
            warnings=warnings
        )


def replace_test_example_file(
    pytester: _Pytester, src: str, target: str
) -> None:
    """Replace a test example file with another file.

    Args:
        pytester (Pytester): The `Pytester` instance.
        src (str): The name of the source file to copy.
        target (str): The name of the target file, which must have
            already been copied to the test directory.
    """
    testdir = pytester.path
    src_p = _ospath.join(testdir, src)
    target_p = _ospath.join(testdir, target)
    _shutil.move(src_p, target_p)


def remove_test_example_file(pytester: _Pytester, file: str) -> None:
    """Remove a test example file.

    Args:
        pytester (Pytester): The `Pytester` instance.
        file (str): The name of the source file to copy.
    """
    testdir = pytester.path
    fp = _ospath.join(testdir, file)
    _os.remove(fp)


@_fixture
def nested_tempdir():
    """A fixture generating a temporary directory protected inside
    another temporary directory.
    """
    with _TemporaryDirectory() as outer:
        with _TemporaryDirectory(dir=outer) as inner:
            yield inner
