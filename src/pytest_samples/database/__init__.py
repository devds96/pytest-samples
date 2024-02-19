"""This module contains the interface to the database for keeping track
of tests that have been run and files containing tests. The main purpose
if this is to decouple the underlying database engine from the main
plugin code and to provide more easily accessible functions to interact
with the database.
"""

__all__ = [
    "TestFile", "TestItem",
    "EngineBase", "Engine",
    "DatabaseError", "IntegrityError", "MultipleResultsFound",
    "NoResultFound", "DetachedInstanceError", "InactiveSessionError",
    "RelativePathError", "EngineDisposedError",
    "enable_logging",
    "Session", "TestFileHashProvider"
]

from ._defs import TestFile, TestItem
from ._engine import EngineBase, Engine
from ._exceptions import DatabaseError, IntegrityError, \
    MultipleResultsFound, NoResultFound, DetachedInstanceError, \
    InactiveSessionError, RelativePathError, EngineDisposedError
from ._logging import enable_logging
from ._session import Session, TestFileHashProvider
