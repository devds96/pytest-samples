"""This file serves as a template for tests of the plugin itself."""

import pytest


@pytest.fixture
def ok_fixture_yield():
    yield object()


@pytest.fixture
def ok_fixture_return():
    return object()


@pytest.fixture
def failing_fixture_1():
    raise RuntimeError


@pytest.fixture
def failing_fixture_2():
    raise IndexError


@pytest.fixture
def failing_fixture_3():
    yield object()
    raise RuntimeError


def test_4_1(ok_fixture_yield: object):
    print("test_4_1")


def test_4_2(ok_fixture_return: object):
    print("test_4_2")


def test_4_3(failing_fixture_1: object):
    print("test_4_3")


def test_4_4(failing_fixture_2: object):
    print("test_4_4"); assert False  # noqa: E702, B011


def test_4_5(failing_fixture_2: object):
    print("test_4_5")


def test_4_6(failing_fixture_3: object):
    print("test_4_6")
