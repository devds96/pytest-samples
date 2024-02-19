import arrow as _arrow
import logging as _logging
import os.path as _ospath
import pytest as _pytest
import warnings as _warnings

from abc import abstractmethod as _abstractmethod
from dataclasses import dataclass as _dataclass
from datetime import timedelta as _timedelta
from enum import IntEnum as _IntEnum
from pluggy import Result as _Result
from pytest import hookimpl as _hookimpl, Item as _Item, \
    TestReport as _TestReport
from typing import Callable as _Callable, Dict as _Dict, \
    Iterator as _Iterator, List as _List, Literal as _Literal, \
    Optional as _Optional, Set as _Set, TYPE_CHECKING as _TYPE_CHECKING

from . import _meta
from ._broker_base import SamplesBrokerBase as _SamplesBrokerBase
from .. import tools as _tools
from ..types import Location as _Location

if _TYPE_CHECKING:  # pragma: no cover
    # These are only used for type hints.
    from ..database import Engine as _Engine, Session as _Session, \
        TestFile as _TestFile, TestFileHashProvider as _TestFileHashProvider


_logger = _logging.getLogger(__name__)
"""The logger for this module."""


_TestResultState = _Literal[
    "passed", "skipped", "failed", "xfailed", "xpassed"  # noqa: F821
]


class _TestResultAction(_IntEnum):
    """Represents the reduced set of results used to decide whether to
    write a test to the database, remove it or do neither.
    """

    WRITE = 0
    """Write the test to the database, it counts as "passed"."""

    DROP = 1
    """Remove the test from the database, it counts as "failed"."""

    IGNORE = 2
    """Ignore the test, for example when it was skipped."""


class TestResultStateNotImplementedWarning(UserWarning):
    """Warning that is issued when a pytest test result state is not
    implemented.
    """
    pass


@_dataclass(frozen=True)
class DatabaseItemFilterResult:

    __slots__ = ("known_test_indices", "last_run_map")

    known_test_indices: _List[int]
    """The indices of items that are known from the database."""

    last_run_map: _Dict[_Item, float]
    """A dictionary mapping test items to the time passed since they
    were last run.
    """


class StatefulSamplesBroker(_SamplesBrokerBase):
    """ABC for samples broker in "stateful" mode."""

    __slots__ = (
        "_rootpath",
        "_db_path",
        "_hash_testfiles",
        "_randomize",
        "_no_pruning",
        "_engine",
        "_reset_on_saturation",
        "_num_tests",
        "_overwrite_broken_db",
        "_session_finished"
    )

    def __init__(
        self,
        rootpath: str,
        soft_timeout: _timedelta,
        seed: _Optional[str],
        db_path: str,
        hash_testfiles: bool,
        randomize: bool,
        no_pruning: bool,
        reset_on_saturation: bool,
        overwrite_broken_db: bool
    ) -> None:
        """Initialize a new `StatefulSamplesBroker`.

        Args:
            rootpath (str): The path to the pytest root.
            soft_timeout (timedelta): The time after which the timeout
                should occur.
            seed (Optional[str]): The seed for the RNG.
            db_path (str): The path to the database to use for the state
                information.
            hash_testfiles (bool): Whether to hash the test files to
                check when tests may have changed.
            randomize (bool): Whether to randomize the "new" tests.
            no_pruning (bool): Whether to keep old test and file entries
                in the database.
            reset_on_saturation (bool): Whether to drop all entries once
                all tets have passed once.
            overwrite_broken_db (bool): Whether to overwrite broken
                database files.
            enable_db_logging (bool): Whether to enable database related
                logging.
        """
        super().__init__(soft_timeout, seed)
        """The total number of tests found."""
        self._rootpath = rootpath
        """The path to the pytest root."""
        self._db_path = db_path
        """Whether to write the state to the database immediately."""
        self._hash_testfiles = hash_testfiles
        """Whether to hash test files."""
        self._randomize = randomize
        """Whether to run the tests in state mode in a random order.
        Known tests will still be moved to the end of the chain.
        """
        self._no_pruning = no_pruning
        """Whether pruning of remnant files and tests is disabled."""
        self._engine: "_Optional[_Engine]" = None
        """Stores the database engine created after all tests are
        collected. Will be instantiated in
        `pytest_collection_modifyitems`.
        """
        self._reset_on_saturation = reset_on_saturation
        """Whether to drop all entries once all tets have passed
        once.
        """
        self._num_tests: _Optional[int] = None
        """The number of tests found."""
        self._overwrite_broken_db = overwrite_broken_db
        """Whether to overwrite broken database files."""

        self._session_finished: bool = False
        """Whether the `pytest_sessionfinish` hook was called."""

        self._post_init()

    def _make_pytest_abspath(self, path: str) -> str:
        """Convert a path relative to the pytest root to an absolute
        path. This is necessary whenever the file system is accessed
        not via pytest because only the paths of test files relative
        to the rootpath are known.

        Args:
            path (str): The path to convert.

        Returns:
            str: The absolute path.
        """
        return _ospath.normpath(_ospath.join(self._rootpath, path))

    def _post_init(self) -> None:  # pragma: no cover
        """Called from the base class's __init__ after all fields
        have been assigned. Derived classes can use this to set
        fields.
        """
        pass

    def _hash_file(self, path: str) -> bytes:
        """Hash a file.

        Args:
            path (str): The path to the file to hash.

        Returns:
            bytes: The hash of the file.
        """
        from .._hashing import hash_file
        abspath = self._make_pytest_abspath(path)
        return hash_file(abspath)

    @classmethod
    def _setup_tables(cls, engine: "_Engine", overwrite: bool) -> None:
        """Set up the database tables.

        Args:
            engine (Engine): The engine.
            overwrite (bool): Whether to overwrite broken database
                files.

        Raises:
            UsageError: If an error occurs during setup.
        """

        second_attempt = False

        while True:
            exception = None

            try:
                engine.setup_tables()
                return
            except Exception as de:
                _logger.exception(
                    "An exception occurred when setup_tables() was called."
                )
                exception = de

            if not overwrite:
                raise _pytest.UsageError(
                    "The provided database file is invalid. The detailed "
                    "exception has been written to the logger."
                ) from exception

            if second_attempt:
                break  # pragma: no cover

            second_attempt = True

            try:
                engine.truncate_database_file()
            except IsADirectoryError as iade:  # pragma: no cover
                raise _pytest.UsageError(
                    "The provided database file path points to a directory."
                ) from iade

        raise _pytest.UsageError(  # pragma: no cover
            "The provided database file is invalid and truncating it did "
            "not resolve the issue. The detailed exception has been "
            "written to the logger."
        )

    @classmethod
    def _setup_engine(cls, path: str, overwrite: bool) -> "_Engine":
        """Set up the database engine.

        Args:
            path (str): The path to the database file.
            overwrite (bool): Whether to overwrite broken database
                files.

        Raises:
            UsageError: If an error occurs during setup.

        Returns:
            Engine: The database engine.
        """
        from ..database import Engine, RelativePathError

        try:
            engine = Engine(path)
        except RelativePathError:  # pragma: no cover
            _logger.exception(
                "A relative path was provided to the Engine constructor."
            )
            # This is an internal error which the user cannot fix
            raise
        except Exception as e:  # pragma: no cover
            _logger.exception("Error with Engine initialization.")
            raise _pytest.UsageError(str(e)) from e

        try:
            cls._setup_tables(engine, overwrite)
        except BaseException:
            engine.dispose()
            raise

        return engine

    @classmethod
    def _compare_against_database(  # noqa: C901
        cls,
        session: "_Session",
        items: _List[_Item],
        hash_func: _Optional[_Callable[[str], bytes]]
    ) -> DatabaseItemFilterResult:
        """Compare the found test items against the database and return
        information regarding the found items and their last run time.
        This may modify the database if a `hash_func` is provided.

        Args:
            session (Session): The database session.
            items (List[Item]): The test items collected by pytest.
            hash_func (Optional[Callable[[str], bytes]]): A function
                providing hashes for the (relative) file paths of test
                items if hashing is requested.

        Returns:
            DatabaseItemFilterResult: An object containing the indices
                of test items found in the database and information
                regarding their last run time.
        """

        @_dataclass(frozen=True)
        class ItemWithFile:

            __slots__ = ("item_index", "pytest_item", "file")

            item_index: int
            """The index of the test item."""

            pytest_item: _Item
            """The test item."""

            file: "_TestFile"
            """The database file entry in which the test item
            appears.
            """

        def filter_with_files() -> _Iterator[ItemWithFile]:
            """Filter out test items which do not have an associated
            file.

            Args:
                items (Iterator[Item]): An iterator iterating over
                    available test items.

            Returns:
                Iterator[ItemWithFile]: An iterable yielding all test
                    items which have an associated file in the database.
            """
            for i, item in enumerate(items):
                file = item.location[0]
                db_file = session.try_get_file(file)
                if db_file is None:
                    # Since the file is not known, the test cannot be
                    # known.
                    continue
                yield ItemWithFile(i, item, db_file)

        items_source = filter_with_files()

        def filter_hashed_and_update(
            items: _Iterator[ItemWithFile], hash_func: _Callable[[str], bytes]
        ) -> _Iterator[ItemWithFile]:
            """Filter out invalidated items from the provided iterable
            and update the file entries' hashes if necessary. Note that
            this may modify the underlying database.

            Args:
                items (Iterator[ItemWithFile]): An iterator iterating
                    over available test items and their files.

            Returns:
                Iterator[ItemWithFile]: An iterable yielding all test
                    items which have an associated file in the database
                    and have not been invalidated due to a changed file
                    hash.
            """
            # Keep track of files whose hash has been updated. The tests
            # will still be considered out of date. This is a shortcut
            # since the test would have been removed from the database
            # anyway and will not be found further down the pipeline.
            ok_file_ids: _Set[int] = set()
            updated_file_ids: _Set[int] = set()

            for item in items:
                file = item.file
                id = file.id
                if id in updated_file_ids:
                    # The file hash has been updated and the test
                    # will not be found below. This is a shortcut.
                    continue
                if id not in ok_file_ids:
                    file_path = item.pytest_item.location[0]
                    hash = hash_func(file_path)
                    if file.last_hash != hash:
                        num_del = session.invalidate_hash(file, hash)
                        _logger.info(
                            "Removed %s test items when updating hash.",
                            num_del
                        )
                        updated_file_ids.add(id)
                    else:
                        ok_file_ids.add(id)
                yield item

        if hash_func is not None:
            items_source = filter_hashed_and_update(items_source, hash_func)

        known_test_indices: _List[int] = list()
        last_run_map: _Dict[_Item, float] = dict()

        now = _arrow.utcnow()

        for item in items_source:
            pytest_test_item = item.pytest_item
            _, lineno, name = pytest_test_item.location
            db_item = session.try_get_item(item.file, lineno, name)
            if db_item is None:
                # No known successful run for this test item.
                continue
            time = (now - db_item.last_run).total_seconds()
            last_run_map[pytest_test_item] = time
            known_test_indices.append(item.item_index)

        return DatabaseItemFilterResult(known_test_indices, last_run_map)

    @_hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: _List[_Item]) -> None:
        """The function called for the pytest "collection_modifyitems"
        hook.

        Args:
            session (Session): The pytest session.
            config (Config): The pytest config.
            items (List[Item]): The list of collected items.
        """

        if self._randomize:
            # XXX: This could be changed by moving the shuffle operation
            # to after the move_idx_to_end-call below. Here, all
            # elements will be shuffled, even those that will be moved
            # to the end of the list anyway. However, the builtin
            # Random does not support shuffle on a sublist
            # out-of-the-box.
            self._shuffle_items(items)

        engine = self._setup_engine(
            self._db_path,
            self._overwrite_broken_db
        )
        self._engine = engine

        num_tests = len(items)
        self._num_tests = num_tests

        if num_tests == 0:
            return

        prune = not self._no_pruning

        with engine.new_session() as session:  # pragma: no branch

            # Keep track of items that we did not find in the database.
            filter_res = self._compare_against_database(
                session,
                items,
                (self._hash_file if self._hash_testfiles else None)
            )

            known_test_indices = filter_res.known_test_indices

            if len(known_test_indices) == num_tests:
                _logger.info("The database is saturated.")
                if self._reset_on_saturation:
                    drop_res = session.drop_all_entries()
                    _logger.info("Saturated: %s", drop_res)
                    return

            if prune:
                # Prune orphaned entries.
                known_locations = set(map(lambda it: it.location, items))
                num = session.prune_items(known_locations)
                _logger.info("Pruned %s disappeared tests.", num)

        _logger.info(
            "Moving %s items to end of list.", len(known_test_indices)
        )
        _tools.move_idx_to_end(
            items,
            known_test_indices,
            sorting_key=filter_res.last_run_map.__getitem__
        )

    def _ensure_engine(self) -> "_Engine":
        """Obtain the database engine or raise an exception.

        Raises:
            RuntimeError: If the engine was not yet assigned.

        Returns:
            Engine: The database engine.
        """
        engine = self._engine
        if engine is None:
            raise RuntimeError("The engine was never assigned.")
        return engine

    @_hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_report_teststatus(self, report: _TestReport):

        # For failed items, this hook is called again after
        # pytest_sessionfinish. But the database will be destroyed after
        # that call. Therefore, do nothing here.
        # XXX: Is this intended behavior of pytest or a bug?
        if self._session_finished:
            yield
            return

        # Either way, this can be called multiple times, for example if
        # an error occurs in the teardown of a fixture that a test may
        # use.

        outcome: _Result = yield
        state, *_ = outcome.get_result()
        if state == '':
            return

        self._process_result(state, report.location)

    @_abstractmethod
    def _process_result(
        self, state: _TestResultState, location: _Location
    ) -> None:
        """Process the result of a tests.

        Args:
            state (_TestResultState): The test result.
            location (_Location): The location of the tests.
        """
        pass

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        """Pytest hook called after all tests have finish.

        Args:
            exitstatus (int): The exit code.
        """
        try:
            self._sessionfinish(exitstatus)
        finally:
            engine = self._engine
            if engine is not None:
                engine.dispose()
            self._session_finished = True

    def _sessionfinish(self, exitstatus: int) -> None:
        """Called after all tests have finish. After the call the engine
        will be disposed.

        Args:
            exitstatus (int): The exit code.
        """
        pass  # pragma: no cover

    def _ensure_num_tests(self) -> int:
        """Obtain the stored number of tests or raise an exception if it
        is not available.

        Returns:
            int: The total number of tests.
        """
        num_tests = self._num_tests
        if num_tests is None:
            raise AssertionError("'_num_tests' was not set.")
        return num_tests

    def _check_test_nums(self, passed: int, failed: int) -> None:
        """Check that the number of passed and failed tests is smaller
        than the total number of tests. Otherwise, write this
        information to the logger as an error.

        Args:
            passed (int): Counted number of passed tests.
            failed (int): Counted number of failed tests.
        """
        num_tests = self._ensure_num_tests()
        if (passed + failed) <= num_tests:
            return
        _logger.error(  # pragma: no cover
            "The number of passed (%s) and failed (%s) tests is larger "
            "than the number of found tests (%s).",
            passed, failed, num_tests
        )

    @classmethod
    def _is_error_exitstatus(cls, exitstatus: int) -> bool:
        """Check whether the exit status indicates an error (but not
        necessarily failed tests).

        Args:
            exitstatus (int): The exit code to check.

        Returns:
            bool: True, if the exit code is not 0 (all tests passed),
                1 (some tests failed), 5 (no tests collected).
        """
        return exitstatus not in (0, 1, 5)

    def _decide_result(
        self, state: _TestResultState
    ) -> _TestResultAction:
        """Decide on whether to store, drop or ignore a test.

        Args:
            state (_TestResultState): The result string from pytset.

        Returns:
            _TestResultAction: The action.
        """
        if state == "skipped":
            return _TestResultAction.IGNORE
        if state in ("passed", "xpassed", "xfailed"):
            return _TestResultAction.WRITE
        if state in ("failed", "error"):
            return _TestResultAction.DROP
        _warnings.warn(  # pragma: no cover # noqa: G010
            f"Unexpected test result state: {state!r}."  # noqa: G004
            "Test will be ignored. This is an error "
            f"in {_meta.PLUGIN_FULL_NAME}.",
            category=TestResultStateNotImplementedWarning
        )
        return _TestResultAction.IGNORE  # pragma: no cover


class ImmediateStatefulSamplesBroker(StatefulSamplesBroker):
    """The stateful plugin that directly writes each test result to the
    database.
    """

    __slots__ = (
        "_num_failed_tests",
        "_num_passed_tests"
    )

    _num_failed_tests: int
    """The number of failed tests."""

    _num_passed_tests: int
    """The number of passed tests."""

    def _post_init(self) -> None:
        """Called from the base class's __init__ after all fields
        have been assigned. Derived classes can use this to set
        fields.
        """
        self._num_failed_tests = 0
        self._num_passed_tests = 0

    def _process_result(
        self, state: _TestResultState, location: _Location
    ) -> None:
        """Process the result of a tests.

        Args:
            state (_TestResultState): The test result.
            location (_Location): The location of the tests.
        """
        action = self._decide_result(state)

        if action == _TestResultAction.IGNORE:
            return

        engine = self._ensure_engine()

        with engine.new_session() as session:
            if action == _TestResultAction.DROP:
                session.try_delete_item(location)
                self._num_failed_tests += 1
                return
            if action == _TestResultAction.WRITE:
                now = _arrow.utcnow()
                file, lineno, testname = location
                db_file = session.try_get_file(file)
                if db_file is None:
                    if self._hash_testfiles:
                        hash = self._hash_file(file)
                    else:
                        hash = None
                    db_file = session.add_file(file, hash)
                session.add_or_update_item(
                    db_file, lineno, testname, now
                )
                self._num_passed_tests += 1
                return
            raise AssertionError(f"Invalid action {action!r}.")

    def _sessionfinish(self, exitstatus: int) -> None:
        """Called after all tests have finish. After the call the engine
        will be disposed.

        Args:
            exitstatus (int): The exit code.
        """
        if self._is_error_exitstatus(exitstatus):
            return  # pragma: no cover

        num_passed = self._num_passed_tests
        num_failed = self._num_failed_tests
        self._check_test_nums(num_passed, num_failed)

        engine = self._ensure_engine()

        num_tests = self._ensure_num_tests()
        if num_passed == num_tests:
            _logger.info("All tests have passed.")
            if self._reset_on_saturation:
                with engine.new_session() as dbsession:
                    drop_res = dbsession.drop_all_entries()
                _logger.info("Saturated: %s", drop_res)
                # Pruning below will not change that the database is
                # empty.
                return

        if self._no_pruning:
            return

        with engine.new_session() as session:
            pfiles = session.prune_files()
            _logger.info("Pruned %s files from the database.", pfiles)


class LazyStatefulSamplesBroker(StatefulSamplesBroker):
    """The stateful plugin that writes the test results to the database
    after all tests have finished.
    """

    __slots__ = (
        "_failed_tests",
        "_passed_tests"
    )

    _failed_tests: _List[_Location]
    """Collects the failed tests."""

    _passed_tests: _List[_Location]
    """Collects the passed tests."""

    def _post_init(self) -> None:
        """Called from the base class's __init__ after all fields
        have been assigned. Derived classes can use this to set
        fields.
        """
        self._failed_tests = list()
        self._passed_tests = list()

    def _process_result(
        self, state: _TestResultState, location: _Location
    ) -> None:
        """Process the result of a tests.

        Args:
            state (_TestResultState): The test result.
            location (_Location): The location of the tests.
        """
        action = self._decide_result(state)

        if action == _TestResultAction.IGNORE:
            return

        if action == _TestResultAction.DROP:
            lst = self._failed_tests
        elif action == _TestResultAction.WRITE:
            lst = self._passed_tests
        else:
            raise AssertionError(f"Invalid action {action!r}.")

        lst.append(location)

    def _sessionfinish(self, exitstatus: int) -> None:
        """Called after all tests have finish. After the call the engine
        will be disposed.

        Args:
            exitstatus (int): The exit code.
        """
        if self._is_error_exitstatus(exitstatus):
            return  # pragma: no cover

        hash_provider: _Optional[_TestFileHashProvider]
        if self._hash_testfiles:

            def hash_provider(test_file: "_TestFile") -> bytes:
                """Provide the hash for a `TestFile`.

                Args:
                    test_file (TestFile): The instance to hash.

                Returns:
                    bytes: The hash of the file
                """
                return self._hash_file(test_file.path)

        else:
            hash_provider = None

        passed_tests = set(self._passed_tests)
        failed_tests = set(self._failed_tests)

        # If for example a test passes, but a fixture it depends on
        # fails on teardown, the item will have been first aded to
        # _passed_tests and later again to _failed_tests. Hence, all
        # duplicates have to be removed from the passed tests.
        passed_tests.difference_update(failed_tests)

        num_passed_tests = len(passed_tests)
        num_failed_tests = len(failed_tests)
        self._check_test_nums(num_passed_tests, num_failed_tests)

        engine = self._ensure_engine()

        num_tests = self._ensure_num_tests()
        if num_passed_tests == num_tests:
            _logger.info("All tests have passed.")
            if self._reset_on_saturation:
                with engine.new_session() as dbsession:
                    drop_res = dbsession.drop_all_entries()
                _logger.info("Saturated: %s", drop_res)
                return

        with engine.new_session() as dbsession:
            result = dbsession.bulk_add_update_remove(
                _arrow.utcnow(),
                passed_tests,
                failed_tests,
                hash_provider,
                prune_files=(not self._no_pruning)
            )

            _logger.info("Updated items test run: %s", result)
