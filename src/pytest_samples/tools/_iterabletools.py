"""This module contains useful functions for iterables."""

from typing import Iterable as _Iterable, Tuple as _Tuple


def count_truefalse(it: _Iterable[bool]) -> _Tuple[int, int]:
    """Separately count the occurences of `True` and `False` in
    and iterable of `bool`s.

    Args:
        it (Iterable[bool]): The iterable to process.

    Returns:
        Tuple[int, int]: The amount of `True` occurrences,
            followed by the amount of `False` occurrences.
    """
    true = 0
    false = 0
    for b in it:
        if b:
            true += 1
        else:
            false += 1
    return true, false
