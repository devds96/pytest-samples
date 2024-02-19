"""This file serves as a template for tests of the plugin itself."""

import pytest


def test_dummy1_2():
    print("test_dummy1")


@pytest.mark.parametrize("it", (0, 1))
def test_dummyp_2(it: int):
    print(f"test_dummyp[{it}]")


@pytest.mark.xfail
class TestClass_2:

    def test_dummyc_2(self):
        print("test_dummyc")


@pytest.mark.xfail
def test_xfail_2():
    assert False  # noqa: B011
