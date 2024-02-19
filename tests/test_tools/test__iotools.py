from hypothesis import given
from hypothesis.strategies import binary
from io import BytesIO

from pytest_samples.tools import copy_fileobj_to_func


@given(data=binary())
def test_copy_fileobj_to_func(data: bytes):
    """Test the `copy_fileobj_to_func` function."""

    res = b''

    def collect(b: bytes):
        nonlocal res
        res += b

    with BytesIO(data) as src:
        copy_fileobj_to_func(src, collect)

    assert res == data
