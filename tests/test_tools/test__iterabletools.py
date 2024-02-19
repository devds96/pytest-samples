from hypothesis import given
from hypothesis.strategies import booleans, lists
from typing import Sequence

from pytest_samples.tools import count_truefalse


@given(iterable=lists(booleans()))
def test_count_truefalse(iterable: Sequence[bool]):
    """Test examples for `count_truefalse`."""

    true_comp = sum(iterable)
    false_comp = len(iterable) - true_comp

    true_c, false_c = count_truefalse(iterable)
    assert true_c == true_comp
    assert false_c == false_comp
