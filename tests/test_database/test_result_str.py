from hypothesis import given
from hypothesis.strategies import integers, one_of, none
from typing import Optional

from pytest_samples.database._session import BulkUpdateResult, \
    DropAllEntriesResult


@given(
    a=integers(),
    b=integers(),
    c=integers(),
    d=one_of(integers(), none())
)
def test_str_BulkUpdateResult(a: int, b: int, c: int, d: Optional[int]):
    """Test the str formatting for `BulkUpdateResult`."""
    s = str(BulkUpdateResult(a, b, c, d))
    assert str(a) in s
    assert str(b) in s
    assert str(c) in s
    assert (str(d) in s) or (d is None)


@given(a=integers(), b=integers())
def test_str_DropAllEntriesResult(a: int, b: int):
    """Test the str formatting for `DropAllEntriesResult`."""
    s = str(DropAllEntriesResult(a, b))
    assert str(a) in s
    assert str(b) in s
