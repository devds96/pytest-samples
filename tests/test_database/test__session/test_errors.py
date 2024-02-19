import pytest

from hypothesis import given
from hypothesis.strategies import text
from typing import Optional

from conftest import InMemoryEngine, optional_integers, testfiles

from pytest_samples.database import DetachedInstanceError, TestFile


@given(file=testfiles(), lineno=optional_integers(), testname=text())
def test_try_get_item_detached_file(
    file: TestFile, lineno: Optional[int], testname: str
):
    """Test that an exception is raised when the `TestFile` provided to
    `Session.try_get_item` is not attached to the session.
    """
    with InMemoryEngine().new_session() as s:
        msg = ".*not attached to a session.*"
        with pytest.raises(DetachedInstanceError, match=msg):
            s.try_get_item(file, lineno, testname)
