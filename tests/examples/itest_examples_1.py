"""This file serves as a template for tests of the plugin itself."""

import pytest


def test_dummy1():
    print("test_dummy1")


def test_dummy2():
    print("test_dummy1")


def test_dummy3():
    print("test_dummy3")


@pytest.mark.parametrize("it", (0, 1, 2))
def test_dummyp(it: int):
    print(f"test_dummyp[{it}]")


class TestClass:

    def test_dummyc(self):
        print("test_dummyc")


@pytest.mark.xfail
def test_xfail():
    raise RuntimeError


@pytest.mark.xfail
def test_xpass():
    pass


def test_fail():
    assert False  # noqa: B011


def test_error():
    raise ValueError
