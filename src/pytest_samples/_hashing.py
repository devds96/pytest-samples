"""This module contains functions for hashing files."""

import hashlib as _hashlib
import sys as _sys

if _sys.version_info >= (3, 9):
    import functools as _functools

from io import BufferedReader as _BufferedReader

from . import tools as _tools


def hash_fileobj(fileobj: _BufferedReader) -> bytes:
    """Compute a non-security relevant md5 hash of a fileobj.

    Args:
        fileobj (str): The fileobj to hash.

    Returns:
        bytes: The digest.
    """
    generator = _hashlib.md5
    if _sys.version_info >= (3, 9):
        generator = _functools.partial(generator, usedforsecurity=False)
    md5 = generator()
    _tools.copy_fileobj_to_func(fileobj, md5.update)
    return md5.digest()


def hash_file(path: str) -> bytes:
    """Compute a non-security relevant md5 hash of a file.

    Args:
        path (str): The path to the file.

    Returns:
        bytes: The digest.
    """
    with open(path, "rb") as ifi:
        return hash_fileobj(ifi)
