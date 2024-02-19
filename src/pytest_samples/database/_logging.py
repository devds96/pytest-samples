import logging as _logging


def enable_logging(level=_logging.INFO) -> None:  # pragma: no cover
    """Enable info logging for the database connections.

    Args:
        level (Level): The log level.
    """
    _logging.getLogger("sqlalchemy.orm").setLevel(level)
    _logging.getLogger("sqlalchemy.engine").setLevel(level)
