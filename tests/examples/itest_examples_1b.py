"""This file serves as a template for tests of the plugin itself."""

import pytest


def test_dummy1():
    print("test_dummy1"); assert False  # noqa: E702, B011


def test_dummy2_othername():
    print("test_dummy2_othername"); assert False  # noqa: E702, B011


def test_dummy3_othername():
    print("test_dummy3_othername")


@pytest.mark.parametrize("it", (-1, 1, 2, 3))
def test_dummyp(it: int):
    print(f"test_dummyp[{it}]"); assert it != 1  # noqa: E702


class TestClass:

    def test_dummyc(self):
        print("test_dummyc")


@pytest.mark.xfail
def test_xfail():
    assert True  # noqa: ULA001


@pytest.mark.xfail
def test_xpass():
    assert False  # noqa: B011


def test_fail():
    pass
