__all__ = [
    "DatabaseError", "IntegrityError", "MultipleResultsFound",
    "NoResultFound",
    "DetachedInstanceError",
    "InactiveSessionError",
    "RelativePathError",
    "EngineDisposedError"
]

from sqlalchemy.exc import DatabaseError, IntegrityError, \
    MultipleResultsFound, NoResultFound
from sqlalchemy.orm.exc import DetachedInstanceError


class InactiveSessionError(RuntimeError):
    """An exception that is raised when an inactive session was
    accessed.
    """
    pass


class RelativePathError(OSError):
    """An exception that is raised when a relative path is provided to
    construct the engine.
    """
    pass


class EngineDisposedError(RuntimeError):
    """An exception that is raised when an `Engine` is accessed after
    it was disposed.
    """
    pass
