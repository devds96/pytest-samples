"""This module contains tool functions."""

__all__ = [
    "move_idx_to_end",
    "copy_fileobj_to_func",
    "count_truefalse"
]


from ._collectiontools import move_idx_to_end
from ._iotools import copy_fileobj_to_func
from ._iterabletools import count_truefalse
