import shutil as _shutil

from dataclasses import dataclass as _dataclass
from typing import Any as _Any, Callable as _Callable, IO as _IO


WriteFunction = _Callable[[bytes], _Any]
"""Function signature of an io "write" function."""


@_dataclass(frozen=True)
class _MockTargetFileobj:
    """An object mocking a fileobj with a "write" function."""

    __slots__ = ("write",)

    write: WriteFunction
    """The write function."""


def copy_fileobj_to_func(
    fileobj: _IO[bytes],
    func: _Callable[[bytes], _Any],
    length: int = 0
):
    """Copy a fileobj to a function accepting bytes. This imitates
    `shutil.copyfileobj` for function targets.

    Args:
        fileobj (IO[bytes]): The fileobj to copy.
        func (Callable[[bytes], Any]): The function to write to.
        length (int, optional): The number of bytes to write. Defaults
            to 0, which will write all bytes.
    """
    target = _MockTargetFileobj(func)
    _shutil.copyfileobj(fileobj, target, length)
