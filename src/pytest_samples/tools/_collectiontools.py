"""This module contains tools for collections."""

from typing import Any as _Any, Callable as _Callable, \
    Iterable as _Iterable, List as _List, Optional as _Optional, \
    Protocol as _Protocol, TypeVar as _TypeVar, Union as _Union


_T = _TypeVar("_T")


# It does not seem like SupportsRichComparison is exposed anywhere from
# the python library. Therefore, _HasLT and _HasGT are implemented
# below.


class _HasLT(_Protocol):
    """Protocol for an object supporting __lt__."""

    def __lt__(self, other: _Any) -> bool:
        pass


class _HasGT(_Protocol):
    """Protocol for an object supporting __gt__."""

    def __gt__(self, other: _Any) -> bool:
        pass


_KeyFunction = _Union[_Callable[[_T], _HasLT], _Callable[[_T], _HasGT]]
"""Type of the functions that provide a sorting key for elements in a
sequence.
"""


def move_idx_to_end(
    src: _List[_T],
    idx: _Iterable[int],
    *,
    sorting_key: _Optional[_KeyFunction[_T]] = None
) -> None:
    """Move a certain set of elements at given indices in a list to the
    end of said list. By default, relative orderings will be preserved,
    but a key function can be provided to determine the ordering of the
    shifted elements.

    Args:
        src (List[T]): The list to modify in-place.
        idx (Iterable[int]): The indices to shift to the end. Negative
            indices will lead to an exception. The indices must be
            unique.
        sorting_key (KeyFunction[T], optional): A function that assings
            a key to each element of `src` that should be shifted to
            determine the ordering of the elements after the non-shifted
            elements.

    Raises:
        IndexError: If negative indices appear in `idx`. If indices
            appearing in `idx` are out-of-bounds with respect to `src`.
        ValueError: If there are duplicate indices in `idx`.
    """

    # Check if there is at least one element in the idx iterable.
    try:
        next(iter(idx))
    except StopIteration:
        return

    idx_b = sorted(idx, reverse=True)
    if idx_b[-1] < 0:
        raise IndexError("There were negative indices in 'idx'.")

    def checked_indices():
        prev_idx = None
        for i in idx_b:
            if i == prev_idx:
                raise ValueError("There were duplicate indices in 'idx'.")
            yield i
            prev_idx = i

    removed = [src.pop(i) for i in checked_indices()]

    if sorting_key is None:
        removed.reverse()
    else:
        removed.sort(key=sorting_key)

    src[:] = src + removed
