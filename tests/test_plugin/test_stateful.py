import pytest

from itertools import combinations
from os import path as ospath
from pytest import ExitCode, Item, Pytester, RunResult
from pytest_mock import MockerFixture
from random import Random
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple

from datetime import timedelta

from conftest import assert_database_entries, DatabaseMocked, \
    ExamplesFile1, ExamplesFile1b, ExamplesFile1b2, ExamplesFile2, \
    ExamplesFiles123, ExamplesFile4, OnDiskDatabase, \
    remove_test_example_file, replace_test_example_file, run_pytest

from pytest_samples.database import TestFile, TestItem
from pytest_samples.plugin import CmdFlags, SamplesBrokerBase
from pytest_samples.types import Location


def run_pytest_stateful(
    pytester: Pytester, *args: str, timeout: str
) -> RunResult:
    """Run pytest with the plugin in "stateful" mode.

    Args:
        pytester (Pytester): The `Pytester` instance.
        timeout (str): The timeout argument.

    Returns:
        RunResult: The produced result.
    """
    return run_pytest(
        pytester, timeout, f"{CmdFlags.mode}=stateful", *args
    )


def test_stateful_no_tests(
    pytester: Pytester, database_mocked: DatabaseMocked
):
    """Check the timeout in "stateful" mode. There are no tests."""
    args = list(database_mocked.args)
    result = run_pytest_stateful(pytester, *args, timeout="off")
    assert result.ret == ExitCode.NO_TESTS_COLLECTED


@pytest.mark.parametrize("seed", (None, 'a', '1'))
@pytest.mark.parametrize("randomize", (True, False))
def test_stateful(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    mocker: MockerFixture,
    seed: Optional[str],
    randomize: bool
):
    """Test the randomize functionality."""

    for fn in ExamplesFiles123.FILENAMES:
        pytester.copy_example(fn)

    args = list(database_mocked.args)

    if seed is not None:
        args.append(f"{CmdFlags.seed}={seed}")

    if randomize:
        args.append(CmdFlags.randomize)

    called = False

    def mocked_shuffle(self: Random, x: List[Item]):
        for item in x:
            assert isinstance(item, Item)
        nonlocal called
        called = True
        if seed is not None:
            comp = Random(seed)
            assert self.getstate() == comp.getstate()
        assert len(x) == ExamplesFiles123.NUM_ITEMS

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    assert not (called ^ randomize)
    database_mocked.assert_no_truncate_call()
    ExamplesFiles123.assert_result(result)
    assert_database_entries(
        database_mocked.engine, ExamplesFiles123.FULL_RESULT
    )


@pytest.mark.parametrize("write_immediately", (True, False))
@pytest.mark.parametrize("reset_on_saturation", (True, False))
def test_stateful_reset_on_saturation(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    write_immediately: bool,
    reset_on_saturation: bool
):
    """Test that a reset may or may not occur after all tests have
    passed.
    """

    # All tests from the second example file pass, xfail or xpass.
    pytester.copy_example(ExamplesFile2.FILENAME)

    args = list(database_mocked.args)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    if reset_on_saturation:
        args.append(CmdFlags.reset_on_saturation)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    database_mocked.assert_no_truncate_call()
    ExamplesFile2.assert_result(result)

    engine = database_mocked.engine
    inner_engine = engine.get_underlying_engine()

    with Session(inner_engine) as session:
        num_files = session.query(TestFile).count()
        num_tests = session.query(TestItem).count()

    if reset_on_saturation:
        assert num_files == 0
        assert num_tests == 0
    else:
        assert num_files == 1
        assert num_tests == 5


@pytest.mark.parametrize("hash_testfiles", (True, False))
@pytest.mark.parametrize("write_immediately", (True, False))
@pytest.mark.parametrize("reset_on_saturation", (True, False))
def test_stateful_test_rerun(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    hash_testfiles: bool,
    write_immediately: bool,
    reset_on_saturation: bool
):
    """Test that test items are properly preserved or dropped with a
    rerun of the tests.
    """

    # All tests from the second example file pass, xfail or xpass.
    pytester.copy_example(ExamplesFile2.FILENAME)

    args = list(database_mocked.args)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    if hash_testfiles:
        args.append(CmdFlags.hash_testfiles)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    database_mocked.assert_no_truncate_call()
    ExamplesFile2.assert_result(result)

    engine = database_mocked.engine
    inner_engine = engine.get_underlying_engine()

    if hash_testfiles:
        with Session(inner_engine) as dbsession:
            tfi = dbsession.query(TestFile).one()
            assert ospath.basename(tfi.path) == ExamplesFile2.FILENAME
            h = tfi.last_hash
            assert h is not None
            ExamplesFile2.assert_MD5_hash(h)

    with Session(inner_engine) as session:
        num_files = session.query(TestFile).count()
        num_tests = session.query(TestItem).count()

    assert num_files == 1
    assert num_tests == 5

    if reset_on_saturation:
        # The database will now be saturated from the beginning.
        args.append(CmdFlags.reset_on_saturation)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    database_mocked.assert_no_truncate_call()
    ExamplesFile2.assert_result(result)

    engine = database_mocked.engine

    with Session(inner_engine) as session:
        num_files = session.query(TestFile).count()
        num_tests = session.query(TestItem).count()

    if reset_on_saturation:
        assert num_files == 0
        assert num_tests == 0
    else:
        assert num_files == 1
        assert num_tests == 5


@pytest.mark.parametrize("which_one", range(11))
@pytest.mark.parametrize("write_immediately", (True, False))
def test_stateful_timeout_immediately(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    mocker: MockerFixture,
    write_immediately: bool,
    which_one: int
):
    """Test the timeout functionality with the timeout set to 0s and
    that at least one test gets executed.
    """

    pytester.copy_example(ExamplesFile1.FILENAME)

    args = list(database_mocked.args)

    # We use "randomize" to gain access to the Random.shuffle function
    # and select the test we want to execute (the one moved to the
    # front of the list)
    args.append(CmdFlags.randomize)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    run_test = None
    test_lno = None

    def mocked_shuffle(self: Random, x: List[Item]):
        assert len(x) == 11
        w = x.pop(which_one)
        x.insert(0, w)
        nonlocal run_test
        nonlocal test_lno
        _, test_lno, run_test = w.location

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    result = run_pytest_stateful(pytester, *args, timeout="0s")

    assert run_test is not None
    database_mocked.assert_no_truncate_call()
    ExamplesFile1.assert_outcome_some((run_test,), result)

    database_structure = {
        ExamplesFile1.FILENAME: {
            run_test: ExamplesFile1.RESULTS[run_test]
        }
    }

    assert_database_entries(
        database_mocked.engine,
        database_structure,
        remove_empty_files=True
    )


@pytest.mark.parametrize("which", combinations(range(11), 2))
@pytest.mark.parametrize("write_immediately", (True, False))
def test_stateful_timeout_after_second(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    mocker: MockerFixture,
    write_immediately: bool,
    which: Tuple[int, int]
):
    """Test the timeout functionality by causing a timeout after the
    second test. This test is implemented differently than
    `test_stateful_timeout_immediately`.
    """

    pytester.copy_example(ExamplesFile1.FILENAME)

    args = list(database_mocked.args)

    # We use "randomize" to gain access to the Random.shuffle function
    # and select the test we want to execute (the one moved to the
    # front of the list)
    args.append(CmdFlags.randomize)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    run_tests: List[Location] = list()

    def mocked_shuffle(self: Random, test_items: List[Item]):
        assert len(test_items) == 11
        selected_items: List[Item] = list()
        for i in which:
            w = test_items[i]
            run_tests.append(w.location)
            selected_items.append(w)
        for i in sorted(which, reverse=True):
            del test_items[i]
        for item in selected_items:
            test_items.insert(0, item)

    mocker.patch("random.Random.shuffle", new=mocked_shuffle)

    num1 = 0

    original = SamplesBrokerBase._prepare_item_check_timeout

    def prepare_item_check_timeout(
        self: SamplesBrokerBase, item: Item
    ) -> None:
        nonlocal num1
        if num1 <= 1:
            self._soft_timeout = timedelta.max
        elif num1 >= 2:
            self._soft_timeout = timedelta(0)
        num1 += 1
        return original(self, item)

    mocker.patch(
        (
            "pytest_samples.plugin._broker_base.SamplesBrokerBase"
            "._prepare_item_check_timeout"
        ),
        new=prepare_item_check_timeout
    )

    result = run_pytest_stateful(pytester, *args, timeout="off")

    run_test_names = [t[2] for t in run_tests]

    assert len(run_tests) == 2
    database_mocked.assert_no_truncate_call()
    ExamplesFile1.assert_outcome_some(run_test_names, result)

    database_structure = {
        ExamplesFile1.FILENAME: {
            k: ExamplesFile1.RESULTS[k] for k in run_test_names
        }
    }

    assert_database_entries(
        database_mocked.engine,
        database_structure,
        remove_empty_files=True
    )


@pytest.mark.parametrize("overwrite_broken_db", (True, False))
@pytest.mark.parametrize("write_immediately", (True, False))
def test_stateful_ondisk_broken_db(
    pytester: Pytester,
    ondisk_database: OnDiskDatabase,
    overwrite_broken_db: bool,
    write_immediately: bool
):
    """Test error and overwrite with a broken database file on disk."""

    pytester.copy_example(ExamplesFile1.FILENAME)

    # pass then fail with or without changed file!
    ondisk_database.destroy_file(100)

    args = list(ondisk_database.args)

    if overwrite_broken_db:
        args.append(CmdFlags.overwrite_broken_db)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    if overwrite_broken_db:
        ExamplesFile1.assert_result(result)
        assert_database_entries(
            ondisk_database, {
                ExamplesFile1.FILENAME: ExamplesFile1.RESULTS
            }
        )
    else:
        assert result.ret == ExitCode.USAGE_ERROR
        # Check that the file has not been modified
        ondisk_database.assert_all_zeros(100)


@pytest.mark.parametrize("hash_testfiles", (True, False))
@pytest.mark.parametrize("write_immediately", (True, False))
@pytest.mark.parametrize("reset_on_saturation", (True, False))
@pytest.mark.parametrize("no_pruning", (True, False))
def test_stateful_changing_tests(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    hash_testfiles: bool,
    write_immediately: bool,
    reset_on_saturation: bool,
    no_pruning: bool
):
    """Test the behavior with changing tests."""

    for fn in ExamplesFiles123.FILENAMES:
        pytester.copy_example(fn)

    args = list(database_mocked.args)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    if hash_testfiles:
        args.append(CmdFlags.hash_testfiles)

    if no_pruning:
        args.append(CmdFlags.no_pruning)

    if reset_on_saturation:
        args.append(CmdFlags.reset_on_saturation)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    database_mocked.assert_no_truncate_call()
    ExamplesFiles123.assert_result(result)

    engine = database_mocked.engine

    assert_database_entries(engine, ExamplesFiles123.FULL_RESULT)

    pytester.copy_example(ExamplesFile1b.FILENAME)
    replace_test_example_file(
        pytester, ExamplesFile1b.FILENAME, ExamplesFile1.FILENAME
    )
    remove_test_example_file(pytester, ExamplesFile2.FILENAME)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    database_mocked.assert_no_truncate_call()
    ExamplesFile1b.assert_result(result)

    if not no_pruning:
        assert_database_entries(
            engine, {
                ExamplesFile1.FILENAME: ExamplesFile1b.RESULTS
            }
        )
        return

    results = {
        ExamplesFile2.FILENAME: ExamplesFile2.RESULTS
    }

    if not hash_testfiles:
        results[ExamplesFile1.FILENAME] = dict(
            **ExamplesFile1b.RESULTS, **ExamplesFile1b2.REMAINDERS
        )
    else:
        results[ExamplesFile1.FILENAME] = ExamplesFile1b.RESULTS

    assert_database_entries(engine, results)


def test_stateful_with_fixtures(
    pytester: Pytester, database_mocked: DatabaseMocked
):
    """Perform the test in "stateful" mode where the tests rely on
    fixtures which may fail.
    """

    pytester.copy_example(ExamplesFile4.FILENAME)

    args = list(database_mocked.args)

    result = run_pytest_stateful(pytester, *args, timeout="off")

    ExamplesFile4.assert_result(result)
    assert_database_entries(
        database_mocked.engine, {
            ExamplesFile4.FILENAME: ExamplesFile4.RESULTS
        }
    )


@pytest.mark.parametrize("hash_testfiles", (True, False))
@pytest.mark.parametrize("write_immediately", (True, False))
def test_stateful_test_rerun_different_test(
    pytester: Pytester,
    database_mocked: DatabaseMocked,
    mocker: MockerFixture,
    hash_testfiles: bool,
    write_immediately: bool
):
    """Test the behavior of a rerun where different tests will be run,
    even though the test file is unchanged.
    """

    # All tests from the second example file pass, xfail or xpass.
    pytester.copy_example(ExamplesFile1.FILENAME)

    passing = ExamplesFile1.TWO_PASSING_ITEMS

    args = list(database_mocked.args)

    if write_immediately:
        args.append(CmdFlags.write_immediately)

    if hash_testfiles:
        args.append(CmdFlags.hash_testfiles)

    num1 = 0

    def prepare_item_check_timeout_1(
        self: SamplesBrokerBase, item: Item
    ) -> None:
        if item.location[2] in passing:
            nonlocal num1
            num1 += 1
            return
        self._mark_skip(item)

    mocker.patch(
        (
            "pytest_samples.plugin._broker_base.SamplesBrokerBase"
            "._prepare_item_check_timeout"
        ),
        new=prepare_item_check_timeout_1
    )

    result = run_pytest_stateful(pytester, *args, timeout="off")

    assert num1 == 2
    database_mocked.assert_no_truncate_call()
    result.assert_outcomes(
        passed=2, skipped=(ExamplesFile1.NUM_ITEMS - 2)
    )
    assert_database_entries(
        database_mocked.engine, {ExamplesFile1.FILENAME: passing}
    )

    num2 = 0
    # Count the items before the previously passed once to make sure the
    # passed items are at the end of the test chain.
    add_before = True
    before = 0

    def prepare_item_check_timeout_2(
        self: SamplesBrokerBase, item: Item
    ) -> None:
        nonlocal add_before
        if item.location[2] not in passing.keys():
            if add_before:
                nonlocal before
                before += 1
            return
        add_before = False
        nonlocal num2
        num2 += 1
        self._mark_skip(item)

    mocker.patch(
        (
            "pytest_samples.plugin._broker_base.SamplesBrokerBase"
            "._prepare_item_check_timeout"
        ),
        new=prepare_item_check_timeout_2
    )

    result = run_pytest_stateful(pytester, *args, timeout="off")

    assert num2 == 2
    assert before == ExamplesFile1.NUM_ITEMS - 2
    database_mocked.assert_no_truncate_call()
    result.assert_outcomes(
        passed=5,
        xfailed=1,
        failed=2,
        xpassed=1,
        skipped=2
    )

    assert_database_entries(
        database_mocked.engine, {
            ExamplesFile1.FILENAME: ExamplesFile1.RESULTS
        }
    )
