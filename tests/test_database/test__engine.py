import pytest

from hypothesis import given
from typing import Callable

from pytest_samples.database import Engine, EngineBase, \
    EngineDisposedError, RelativePathError

from conftest import InMemoryEngine, rel_str_paths


def test_engine_empty_str_raises():
    """Test that an exception is raised if the database path is
    empty.
    """
    with pytest.raises(ValueError, match=".*path was empty.*"):
        Engine('')


@given(path=rel_str_paths())
def test_engine_rel_path_raises(path: str):
    """Test that providing a relative path to the engine raises an
    exception.
    """
    with pytest.raises(RelativePathError, match=".*relative path.*"):
        Engine(path)


def test_engine_directory_path_raises(nested_tempdir: str):
    """Test that an exception is raised if the path provided to the
    `Engine` constructor points to a directory.
    """
    # In case the file gets created for some reason, it will be
    # created inside the outer temporary directory and will be removed
    # after the context ends.
    msg = ".*points to a directory.*"
    with pytest.raises(IsADirectoryError, match=msg):
        Engine(nested_tempdir)


@pytest.mark.parametrize(
    "from_where", (EngineBase.setup_tables, EngineBase.new_session)
)
def test_access_after_dispose_raises(from_where: Callable):
    """Test that an exception is raised if the engine is accessed after
    `dispose` was called.
    """

    try:
        ime = InMemoryEngine()
    finally:
        ime.dispose()

    func = getattr(ime, from_where.__name__)
    with pytest.raises(EngineDisposedError, match=".*already disposed.*"):
        func()
