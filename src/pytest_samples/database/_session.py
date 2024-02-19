import dataclasses as _dataclasses
import functools as _functools
import itertools as _itertools
import logging as _logging
import sqlalchemy as _sqlalchemy
import sqlalchemy.orm as _orm

from arrow import Arrow as _Arrow
from contextlib import AbstractContextManager as _AbstractContextManager
from dataclasses import dataclass as _dataclass
from sqlalchemy import Engine as _Engine
from types import TracebackType as _TracebackType
from typing import Callable as _Callable, Iterable as _Iterable, \
    Optional as _Optional, Set as _Set, Type as _Type

from . import _exceptions
from ._defs import TestFile as _TestFile, TestItem as _TestItem
from ..types import Location as _Location
from .. import tools as _tools


_logger = _logging.getLogger(__name__)
"""The logger for this module."""


@_dataclass(frozen=True)
class BulkUpdateResult:
    """Contains information regarding bulk updates."""

    __slots__ = ("added", "updated", "removed", "pruned_files")

    added: int
    """The number of added items."""

    updated: int
    """The number of updated items."""

    removed: int
    """The number of removed items."""

    pruned_files: _Optional[int]
    """The number of pruned files."""

    def __str__(self) -> str:
        """Convert the instance to a str for logging."""
        field_names = (f.name for f in _dataclasses.fields(self))
        value_name = (
            (getattr(self, n), n.replace('_', ' ')) for n in field_names
        )
        fvname = (vn for vn in value_name if vn[0] is not None)
        enumeration = (f"{vn[0]} {vn[1]}" for vn in fvname)
        return ", ".join(enumeration)


@_dataclass(frozen=True)
class DropAllEntriesResult:
    """Contains information regarding the number of all dropped files
    and items.
    """

    __slots__ = ("files_dropped", "tests_dropped")

    files_dropped: int
    """The number of dropped files."""

    tests_dropped: int
    """The number of dropped test items."""

    def __str__(self) -> str:
        """Convert the instance to a str for logging."""
        field_names = (f.name for f in _dataclasses.fields(self))
        value_name = (
            (getattr(self, n), n.replace('_', ' ')) for n in field_names
        )
        enumeration = (f"{vn[0]} {vn[1]}" for vn in value_name)
        return ", ".join(enumeration)


TestFileHashProvider = _Callable[[_TestFile], bytes]
"""A function providing the hash for a `TestFile`. The `last_hash` field
of the passed instance is undefined.
"""


class Session(_AbstractContextManager):
    """The session objects that basically act as the database
    connection.
    """

    __slots__ = ("_engine", "_session")

    def __init__(self, engine: _Engine) -> None:
        """Initialize a new Session using the provided engine. The
        connection will start once `__enter__` has been called.

        Args:
            engine (Engine): The engine for the connection.
        """
        self._engine = engine
        self._session: _Optional[_orm.Session] = None

    def _ensure_session(self) -> _orm.Session:  # pragma: no cover
        """Ensure that the session object has an active connection and
        return the underlying database sqlalchemy `orm.Session`.

        Raises:
            InactiveSessionError: If the session was not startet by
                calling `__enter__`.

        Returns:
            orm.Session: The sqlalchemy `orm.Session` object this
                `Session` is based on.
        """
        s = self._session
        if s is not None:
            return s
        raise _exceptions.InactiveSessionError(
            "The session object was not started with __enter__."
        )

    def __enter__(self):
        """Start the connection in a conext manager.

        Returns:
            self
        """
        self._session = _orm.Session(self._engine)
        return self

    def __exit__(
        self,
        exc_type: _Optional[_Type[BaseException]],
        exc_value: _Optional[BaseException],
        traceback: _Optional[_TracebackType]
    ) -> None:
        """Close the connection by exiting the context.

        Args:
            exc_type (Optional[Type[BaseException]]): The exception type
                or None if no exception occured.
            exc_value (Optional[BaseException]): The exception value
                or None if no exception occured.
            traceback (Optional[TracebackType]): The traceback or None
                if no exception occured.
        """
        dbsession = self._session
        if dbsession is None:  # pragma: no cover
            # I am not sure if this should raise an exception. This
            # means that __exit__ is called but __enter__ was never
            # called.
            _logger.warning("__exit__ was called, but _session was None.")
            return
        dbsession.__exit__(exc_type, exc_value, traceback)

    @classmethod
    def _try_get_file(
        cls, dbsession: _orm.Session, path: str
    ) -> _Optional[_TestFile]:
        """Search the database for a file containing tests.

        Args:
            path (str): The known path to the file.

        Raises:
            MultipleResultsFound: If multiple entries are found for
                `path`. This should not happen since the path column
                must be unique.

        Returns:
            Optional[TestFile]: A `TestFile` if the file was found and
                None otherwise.
        """
        stmt = _sqlalchemy.select(_TestFile).where(_TestFile.path == path)
        result = dbsession.execute(stmt)
        return result.scalar_one_or_none()

    def try_get_file(self, path: str) -> _Optional[_TestFile]:
        """Search the database for a file containing tests.

        Args:
            path (str): The known path to the file.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.
            MultipleResultsFound: If multiple entries are found for
                `path`. This should not happen since the path column
                must be unique.

        Returns:
            Optional[TestFile]: A `TestFile` if the file was found and
                None otherwise.
        """
        session = self._ensure_session()
        return self._try_get_file(session, path)

    def add_file(self, path: str, hash: _Optional[bytes]) -> _TestFile:
        """Add a new file.

        Args:
            path (str): The path of the file to add.
            hash (Optional[bytes]): The hash of the file if it should be
                added or None otherwise.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.
            IntegrityError: If the `path` is already stored.

        Returns:
            TestFile: The newly added `TestFile` instance with its id
                set according to the new entry.
        """
        instance = _TestFile(path=path, last_hash=hash)
        dbsession = self._ensure_session()
        dbsession.add(instance)
        dbsession.commit()
        return instance

    @classmethod
    def _try_get_item(
        cls,
        dbsession: _orm.Session,
        file: _TestFile,
        lineno: _Optional[int],
        testname: str
    ) -> _Optional[_TestItem]:
        """Search the database for a test item.

        Args:
            dbsession (orm.Session): The session object.
            file (TestFile): The file the test item should be found in.
            lineno (Optional[int]): The line number of the test.
            testname (str): The name of the test.

        Raises:
            DetachedInstanceError: If the provided `file` is not
                attached to a `Session`.
            MultipleResultsFound: If multiple entries are found that
                match the item. This should not happen since the three
                identifying columns must be unique together.

        Returns:
            Optional[TestItem]: A `TestItem` if the test item was found
                and None otherwise.
        """
        if file not in dbsession:
            raise _exceptions.DetachedInstanceError(
                "The file was not attached to a session."
            )
        stmt = _sqlalchemy.select(_TestItem).where(
            _TestItem.file == file,
            _TestItem.lineno == lineno,
            _TestItem.testname == testname
        )
        result = dbsession.execute(stmt)
        return result.scalar_one_or_none()

    def try_get_item(
        self, file: _TestFile, lineno: _Optional[int], testname: str
    ) -> _Optional[_TestItem]:
        """Search the database for a test item.

        Args:
            file (TestFile): The file the test item should be found in.
            lineno (Optional[int]): The line number of the test.
            testname (str): The name of the test.

        Raises:
            DetachedInstanceError: If the provided `file` is not
                attached to a `Session`.
            InactiveSessionError: If the session was not started by
                calling __enter__.
            MultipleResultsFound: If multiple entries are found that
                match the item. This should not happen since the three
                identifying columns must be unique together.

        Returns:
            Optional[TestItem]: A `TestItem` if the test item was found
                and None otherwise.
        """
        dbsession = self._ensure_session()
        return self._try_get_item(dbsession, file, lineno, testname)

    def invalidate_hash(self, file: _TestFile, new_hash: bytes) -> int:
        """Replace the hash of a test file and delete all test items
        that belong to this file.

        Args:
            file (TestFile): The test file to update in-place.
            new_hash (bytes): The new hash to add to the file.

        Raises:
            DetachedInstanceError: If the provided `file` is not
                attached to a `Session`.
            InactiveSessionError: If the session was not started by
                calling __enter__.

        Returns:
            int: The number of deleted `TestItem`s from the
                corresponding table.
        """
        dbsession = self._ensure_session()
        # Since we are removing items from the database, start a
        # transaction
        with dbsession.begin_nested():
            # May raise DetachedInstanceError:
            predicate = _TestItem.file_id == file.id
            # Interestingly, the assignment below and the call to
            # flush() would not raise the exception. Therefore, the
            # predicate is formed above.
            file.last_hash = new_hash
            dbsession.flush()
            # Delete all test items from that file since they may have
            # changed.
            del_stmt = _sqlalchemy.delete(_TestItem).where(predicate)
            num_del_items = dbsession.execute(del_stmt).rowcount
            dbsession.commit()
            return num_del_items

    @classmethod
    def _prune_files(cls, dbsession: _orm.Session) -> int:
        """Prune files that have no tests from the database. Does not
        perform a commit.

        Args:
            dbsession (orm.Session): The orm session.

        Returns:
            int: The number of pruned files after the following commit.
        """
        stmt = _sqlalchemy.delete(_TestFile).where(~_TestFile.items.any())
        fdeleted = dbsession.execute(stmt).rowcount
        return fdeleted

    def prune_files(self) -> int:
        """Prune files that have no tests from the database.

        Args:
            seen_file_ids (Set[int]): The ids (primary keys) of the
                seen files. This should include all added files
                although the contained tests may not actually be run in
                this test iteration.
            seen_test_ids (Set[int]): The ids (primary keys) of the
                seen tests.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.

        Returns:
            int: The number of pruned files.
        """
        dbsession = self._ensure_session()
        with dbsession.begin_nested():
            result = self._prune_files(dbsession)
            dbsession.commit()
            return result

    @classmethod
    def _prune_items(
        cls, dbsession: _orm.Session, known_locations: _Set[_Location]
    ) -> int:
        """Prune items from the database.

        Args:
            dbsession (orm.Session): The session object.
            known_locations (Set[Location]): All known locations where
                items are expected. Items not at these locations will
                be deleted.

        Returns:
            int: The number of deleted items.
        """
        select = _sqlalchemy.select(_TestItem)
        result = dbsession.execute(select)
        scalars = result.scalars()
        partitions = scalars.partitions()
        num_del = 0
        for item in _itertools.chain.from_iterable(partitions):
            loc = item.location
            if loc in known_locations:
                continue
            dbsession.delete(item)
            num_del += 1
        return num_del

    def prune_items(self, known_locations: _Set[_Location]) -> int:
        """Prune items from the database.

        Args:
            known_locations (Set[Location]): All known locations where
                items are expected. Items not at these locations will
                be deleted.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.

        Returns:
            int: The number of deleted `TestItem`s.
        """
        dbsession = self._ensure_session()
        with dbsession.begin_nested():
            result = self._prune_items(dbsession, known_locations)
            dbsession.commit()
        return result

    def add_or_update_item(
        self,
        file: _TestFile,
        lineno: _Optional[int],
        testname: str,
        last_run: _Arrow
    ) -> _TestItem:
        """Add a new item or update its last run time if it already
        exists.

        Args:
            file (TestFile): The file the test item should be found in.
            lineno (Optional[int]): The line number of the test.
            testname (str): The name of the test.
            last_run (Arrow): The time of the last test run.

        Raises:
            DetachedInstanceError: If the provided `file` is not
                attached to a `Session`.
            InactiveSessionError: If the session was not started by
                calling __enter__.
            IntegrityError: If the added item does not fulfill
                uniqueness constraints, which should never happen since
                the item would already be present in the database and
                would be modified instead and would imply that the
                database is corrupted in some form.
            MultipleResultsFound: If multiple files are found with the
                path specified in `location`. If multiple items are
                found that could be updated. These imply that the
                database is corrupted.
            NoResultFound: If no file is found with the path specified
                in `location`.

        Returns:
            TestItem: The new or updated item.
        """
        dbsession = self._ensure_session()

        # May raise DetachedInstanceError or MultipleResultsFound:
        db_item = self._try_get_item(dbsession, file, lineno, testname)
        # What if the file is not in the db?
        if db_item is None:
            db_item = _TestItem(
                file=file,
                lineno=lineno,
                testname=testname,
                last_run=last_run
            )
            dbsession.add(db_item)
        else:
            db_item.last_run = last_run

        dbsession.commit()

        return db_item

    @classmethod
    def _try_delete_item(
        cls, dbsession: _orm.Session, location: _Location
    ) -> bool:
        """Try to delete an item from the database.

        Args:
            location (Location): The test item location.

        Raises:
            MultipleResultsFound: If multiple files are found with the
                path specified in `location`. If multiple items to
                delete are found. These should not happen due to
                uniqueness constraints in the database and would imply
                that it is corrupted in some way.

        Returns:
            bool: If the file was deleted from/present in the database.
        """
        file, lineno, testname = location

        # May raise MultipleResultsFound:
        db_file = cls._try_get_file(dbsession, file)

        # If the file is not in the database, then the item will not be
        # either.
        if db_file is None:
            return False

        stmt = _sqlalchemy.delete(_TestItem).where(
            _TestItem.file == db_file,
            _TestItem.lineno == lineno,
            _TestItem.testname == testname
        )
        rc = dbsession.execute(stmt).rowcount
        if rc < 0:
            raise AssertionError
        if rc > 1:
            raise _exceptions.MultipleResultsFound(
                "Found multiple matching items."
            ) from AssertionError
        return rc == 1

    def try_delete_item(self, location: _Location) -> bool:
        """Try to delete an item from the database.

        Args:
            location (Location): The test item location.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.
            MultipleResultsFound: If multiple files are found with the
                path specified in `location`. If multiple items to
                delete are found. These should not happen due to
                uniqueness constraints in the database and would imply
                that it is corrupted in some way.

        Returns:
            bool: If the file was deleted from/present in the database.
        """
        dbsession = self._ensure_session()
        with dbsession.begin_nested():
            # May raise MultipleResultsFound:
            result = self._try_delete_item(dbsession, location)
            if result:
                dbsession.commit()
        return result

    def bulk_add_update_remove(
        self,
        last_run: _Arrow,
        add_update: _Iterable[_Location],
        try_delete: _Iterable[_Location],
        hash_provider: _Optional[TestFileHashProvider],
        prune_files: bool
    ) -> BulkUpdateResult:
        """Perform a bulk update by adding, updating and deleting test
        items.

        Args:
            last_run (Arrow): The Arrow instance to set as the last run
                time for the test items.
            add_update (Iterable[Location]): The tests to add and update
                with the new `last_run` time.
            try_delete (Iterable[Location]): The items to delete if they
                are present.
            hash_provider (Optional[TestFileHashProvider]): If required,
                a `TestFileHashProvider` for computing the hashes of
                test files. Otherwise None.
            hash_provider (bool): Whether to prune orphaned files from
                the database.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.
            IntegrityError: If the added items do not fulfill uniqueness
                constraints. This should not happen since the second
                appearance of a location would simply lead to an update.
            MultipleResultsFound: If multiple files are found with a
                path specified in one of the location items.
                If multiple items to delete are found. If multiple items
                are found that could be updated. These should not
                happen due to uniqueness constraints in the database and
                would imply that it is corrupted in some way.
            NoResultFound: If no file is found with a path specified in
                the locations for items that should be deleted.

        Returns:
            BulkUpdateResult: An object containing the amount of added,
                updated and deleted items.
        """

        dbsession = self._ensure_session()

        def add_or_update(location: _Location) -> bool:
            """Add a new item or update its last run time if it already
            exists. Does not perform a commit.

            Args:
                location (Location): The test item location.

            Returns:
                bool: Whether the item was already in the database.
            """
            file, lineno, testname = location

            # Get or add the file
            db_file = self.try_get_file(file)
            if db_file is None:
                db_file = _TestFile(path=file, last_hash=None)
                if hash_provider is not None:
                    hash = hash_provider(db_file)
                    db_file.last_hash = hash
                dbsession.add(db_file)
                # The item cannot exist yet if the database is
                # consistent
                db_item = None
            else:
                db_item = self._try_get_item(
                    dbsession, db_file, lineno, testname
                )

            if db_item is None:
                db_item = _TestItem(
                    file=db_file,
                    lineno=lineno,
                    testname=testname,
                    last_run=last_run
                )
                dbsession.add(db_item)
                return False

            db_item.last_run = last_run
            return True

        deleter = _functools.partial(self._try_delete_item, dbsession)

        with dbsession.begin_nested():

            results = map(add_or_update, add_update)
            updated, added = _tools.count_truefalse(results)
            dbsession.flush()

            removed = sum(map(deleter, try_delete))

            if prune_files:
                dbsession.flush()
                pruned = self._prune_files(dbsession)
            else:
                pruned = None

            dbsession.commit()

        return BulkUpdateResult(added, updated, removed, pruned)

    def drop_all_entries(self) -> DropAllEntriesResult:
        """Clean the database completely by dropping all `TestItem` and
        `TestFile` entries.

        Raises:
            InactiveSessionError: If the session was not started by
                calling __enter__.

        Returns:
            DropAllEntriesResult: A result object describing the number
                of dropped entries from each table.
        """

        dbsession = self._ensure_session()

        with dbsession.begin_nested():

            deld_items = dbsession.query(_TestItem).delete()
            deld_files = dbsession.query(_TestFile).delete()

            dbsession.commit()

        return DropAllEntriesResult(deld_files, deld_items)
