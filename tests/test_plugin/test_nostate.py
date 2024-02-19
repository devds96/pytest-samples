import pytest

from pytest import ExitCode, Item, Pytester, RunResult
from pytest_mock import MockerFixture
from random import Random
from typing import List, Optional, Tuple

from conftest import ExamplesFile1, ExamplesFile4, run_pytest

from pytest_samples.plugin import CmdFlags


def run_pytest_nostate(
    pytester: Pytester, *args: str, timeout: str
) -> RunResult:
    """Run pytest with the plugin in "nostate" mode.

    Args:
        pytester (Pytester): The `Pytester` instance.
        timeout (str): The timeout argument.

    Returns:
        RunResult: The produced result.
    """
    return run_pytest(pytester, timeout, f"{CmdFlags.mode}=nostate", *args)


@pytest.mark.parametrize(
    "seed_args", (
        ('', None, 0),
        (f"{CmdFlags.seed}=1", '1', 1),
        (f"{CmdFlags.seed}=1 {CmdFlags.nostate_seeded}", '1', 0),
    )
)
def test_nostate(
    pytester: Pytester,
    seed_args: Tuple[str, Optional[str], int],
    mocker: MockerFixture
):
    """Perform the test in "nostate" mode."""

    pytester.copy_example(ExamplesFile1.FILENAME)
    args, seed, warns = seed_args

    called = False

    def mocked_shuffle(self: Random, x: List[Item]):
        for item in x:
            assert isinstance(item, Item)
        nonlocal called
        called = True
        if seed is not None:
            comp = Random(seed)
            assert self.getstate() == comp.getstate()
        assert len(x) == ExamplesFile1.NUM_ITEMS

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    result = run_pytest_nostate(pytester, *args.split(' '), timeout="off")

    assert called
    ExamplesFile1.assert_result(result, warnings=warns)


@pytest.mark.parametrize("which_one", range(11))
def test_nostate_timeout(
    pytester: Pytester, mocker: MockerFixture, which_one: int
):
    """Check the timeout in "nostate" mode. Only one tests will be
    executed.
    """

    pytester.copy_example("itest_examples_1.py")

    run_test = None

    def mocked_shuffle(self: Random, x: List[Item]):
        assert len(x) == 11
        w = x.pop(which_one)
        x.insert(0, w)
        nonlocal run_test
        run_test = w.location[2]

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    result = run_pytest_nostate(pytester, timeout="0s")

    assert run_test is not None
    ExamplesFile1.assert_outcome_some((run_test,), result)


def test_nostate_no_tests(pytester: Pytester):
    """Check the timeout in "nostate" mode. There are no tests."""
    result = run_pytest_nostate(pytester, timeout="off")
    assert result.ret == ExitCode.NO_TESTS_COLLECTED


def test_nostate_with_fixtures(pytester: Pytester, mocker: MockerFixture):
    """Perform the test in "nostate" mode where the tests rely on
    fixtures which may fail.
    """

    pytester.copy_example(ExamplesFile4.FILENAME)

    called = False

    def mocked_shuffle(self: Random, x: List[Item]):
        nonlocal called
        called = True
        assert len(x) == ExamplesFile4.NUM_ITEMS

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    result = run_pytest_nostate(pytester, timeout="off")

    assert called
    ExamplesFile4.assert_result(result)
