import logging as _logging
import os as _os
import os.path as _ospath
import sqlalchemy as _sqlalchemy

from sqlalchemy import Engine as _Engine

from . import _defs
from . import _exceptions
from ._session import Session as _Session


_logger = _logging.getLogger(__name__)
"""The logger for this module."""


class EngineBase:
    """Base class for the engine which wraps the sqlalchemy engine."""

    __slots__ = ("_engine", "_disposed")

    def __init__(self, inner: _Engine) -> None:
        """Initialize the `_EngineBase`.

        Args:
            inner (_Engine): The underlying `sqlalchemy` Engine.
        """
        self._engine = inner
        """Whether the `setup_tables` was called to set up the
        tables.
        """
        # It is important to track this since it seems like sqlalchemy
        # will just reopen the engine if any action is performed after
        # dispose is called.
        self._disposed: bool = False
        """Whther `dispose` was called."""

    def _ensure_not_disposed(self) -> None:
        """Raise an exception if the `Engine` instance was already
        disposed.

        Raises:
            EngineDisposedError: If the instance was already disposed.
        """
        if self._disposed:
            raise _exceptions.EngineDisposedError(
                "The Engine instance was already disposed."
            )

    # It does not make sense to implement this in a context manager
    # since it is not possible to use this in a context anyway. Instead,
    # the object will be torn down in a different hook function than
    # it was created.
    def dispose(self) -> None:
        """Close the engine."""
        self._engine.dispose()
        self._disposed = True

    def setup_tables(self) -> None:
        """Initialize the tables.

        Raises:
            DatabaseError: If the database is corrupted.
            EngineDisposedError: If the instance was already disposed.
        """
        self._ensure_not_disposed()
        _defs.create_tables(self._engine)

    def new_session(self) -> _Session:
        """Start a new session.

        Raises:
            EngineDisposedError: If the instance was already disposed.
            EngineNotInitializedError: If the `Engine` instance was not
                initialized.

        Returns:
            Session: A new session object.
        """
        self._ensure_not_disposed()
        return _Session(self._engine)


class Engine(EngineBase):
    """The main engine for database connections."""

    __slots__ = ("_path",)

    def __init__(self, path: str) -> None:
        """Initialize a new `Engine` given the file path.

        Args:
            path (str): The file path.

        Raises:
            IsADirectoryError: If the provided path points to an
                existing directory.
            RelativePathError: If the provided path is a relative path.
            ValueError: If `path` is invalid, for example if it is the
                empty `str`.
        """
        if len(path) == 0:
            raise ValueError("The database path was empty.")
        # This allows for the creation of a file named :memory:, which
        # would otherwise create an in-memory database.
        if not _ospath.isabs(path):
            raise _exceptions.RelativePathError(
                "The provided path is a relative path."
            )
        if _ospath.isdir(path):
            raise IsADirectoryError(
                "The database path points to a directory."
            )
        self._path = path
        engine = self.create_engine(path)
        super().__init__(engine)

    @classmethod
    def create_engine(cls, path: str) -> _Engine:
        """Create the inner engine given the path.

        Args:
            path (str): The path to the database file.

        Returns:
            Engine: The sqlalchemy engine for the connections.
        """
        return _sqlalchemy.create_engine(f"sqlite:///{path}")

    def truncate_database_file(self) -> None:
        """Truncate the database file.

        Raises:
            IsADirectoryError: If the provided path is a directory.
            FileNotFoundError: If the file does not exist.
        """
        _logger.info("Truncating database file.")
        _os.truncate(self._path, 0)
