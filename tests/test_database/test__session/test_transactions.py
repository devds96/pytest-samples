import arrow
import pytest

from datetime import timedelta
from sqlalchemy.orm import Session

from pytest_samples.database import TestFile, TestItem

from conftest import InMemoryEngine


def test_try_get_file(populated_engine: InMemoryEngine):
    """Test the `Session.try_get_file` function."""
    with populated_engine.new_session() as s:
        f1 = s.try_get_file("abc")
        assert f1.last_hash == b"123"
        f2 = s.try_get_file("def")
        assert f2.last_hash == b"456"
        f3 = s.try_get_file("ghi")
        assert f3.last_hash is None


def test_try_get_item(populated_engine: InMemoryEngine):
    """Test the `Session.try_get_item` function."""

    with populated_engine.new_session() as s:

        f1 = s.try_get_file("abc")
        assert s.try_get_item(f1, 0, "t1") is not None
        assert s.try_get_item(f1, 1, "t2") is not None
        assert s.try_get_item(f1, 2, "t3") is not None
        assert s.try_get_item(f1, 3, "t4") is not None

        f2 = s.try_get_file("def")
        assert s.try_get_item(f2, 0, "t5") is not None

        f3 = s.try_get_file("ghi")
        # The test below actually belongs to file f2
        assert s.try_get_item(f3, 1, "t6") is None


def test_invalidate_hash(populated_engine: InMemoryEngine):
    """Test the `Session.invalidate_hash` function."""

    with populated_engine.new_session() as s:
        f1 = s.try_get_file("abc")
        assert s.invalidate_hash(f1, b"0123") == 4
        assert f1.last_hash == b"0123"

        # Verify that the other files are unchanged
        f2 = s.try_get_file("def")
        assert f2.last_hash == b"456"
        f3 = s.try_get_file("ghi")
        assert f3.last_hash is None

    # Verify the number of files and items
    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        assert session.query(TestFile).count() == 3
        assert session.query(TestItem).count() == 2


def test_prune_files(populated_engine: InMemoryEngine):
    """Test the `Session.prune` function."""

    with populated_engine.new_session() as s:
        # These do exist:
        s.try_delete_item(("def", 0, "t5"))
        s.try_delete_item(("def", 1, "t6"))
        # These do not exist:
        s.try_delete_item(("def", 1, "t0"))
        s.try_delete_item(("ghi", -1, "t0"))
        # This one does exist in a different file:
        s.try_delete_item(("def", 0, "t1"))
        # This one does not exist and neither does the file:
        s.try_delete_item(("aaa", 0, "t1"))

    # Verify the number of files and items
    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        assert session.query(TestFile).count() == 3

    with populated_engine.new_session() as s:
        # Two files to not have any tests.
        assert s.prune_files() == 2
        assert s.try_get_file("abc") is not None
        assert s.try_get_file("ghi") is None
        assert s.try_get_file("def") is None

    with Session(engine) as session:
        assert session.query(TestFile).count() == 1


def test_prune_items(populated_engine: InMemoryEngine):
    """Test the `Session.prune_items` function."""

    locations = [
        ("abc", 0, "t1"),
        ("abc", 1, "t2"),
        ("abc", 3, "t4")
    ]

    with populated_engine.new_session() as s:
        assert s.prune_items(set(locations)) == 3

    # Verify the number of files and items
    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        assert session.query(TestFile).count() == 3
        assert session.query(TestItem).count() == 3

    with populated_engine.new_session() as s:
        f1 = s.try_get_file("abc")
        assert f1 is not None
        for item in locations:
            _, lineno, testname = item
            it = s.try_get_item(f1, lineno, testname)
            assert it is not None
        assert s.try_get_file("def") is not None
        assert s.try_get_file("ghi") is not None


def test_update_item(populated_engine: InMemoryEngine):
    """Test the update functionality of `Session.add_or_update_item`."""

    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        count_files = session.query(TestFile).count()
        count_items = session.query(TestItem).count()

    with populated_engine.new_session() as s:
        f2 = s.try_get_file("def")
        prev_time = s.try_get_item(f2, 0, "t5").last_run

        # Make sure that "now" is definitely after the fixture was
        # created.
        now = arrow.utcnow() + timedelta(microseconds=1)
        s.add_or_update_item(f2, 0, "t5", now)

    with populated_engine.new_session() as s:
        f2b = s.try_get_file("def")
        now_time = s.try_get_item(f2b, 0, "t5").last_run

    assert now == now_time
    assert prev_time < now_time

    test_try_get_file(populated_engine)
    test_try_get_item(populated_engine)

    with Session(engine) as session:
        assert session.query(TestFile).count() == count_files
        assert session.query(TestItem).count() == count_items


@pytest.mark.parametrize("prune", (False, True))
def test_bulk_add_update_remove(
    populated_engine: InMemoryEngine, prune: bool
):
    """Test `Session.bulk_add_update_remove`."""

    now = arrow.utcnow() + timedelta(microseconds=1)

    add_or_update = [
        # update
        ("abc", 0, "t1"),
        ("abc", 1, "t2"),
        # add
        ("abc", 0, "t1b"),
        ("abc", 1, "t2b"),
        # add, new file
        ("abc_2", 0, "t1_2"),
        ("abc_2", 1, "t2_2"),
    ]

    remove = [
        ("abc", 3, "t4"),
        ("def", 0, "t5"),
        ("def", 1, "t6"),
        # never run yet
        ("ghi", 0, "t7"),
        ("ghi", 1, "t8"),
        # never run yet, new file
        ("ghi2", 10, "t9")
    ]

    # ("abc", 2, "t3") should be unchanged

    with populated_engine.new_session() as s:
        s.bulk_add_update_remove(
            now, add_or_update, remove, None, prune
        )

    if prune:
        # "def" and "ghi" will be removed
        expected_files = 2
    else:
        expected_files = 4

    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        assert session.query(TestItem).count() == 7
        assert session.query(TestFile).count() == expected_files

    with populated_engine.new_session() as s:

        f1 = s.try_get_file("abc")
        assert f1 is not None

        t1 = s.try_get_item(f1, 0, "t1")
        assert t1 is not None
        assert t1.last_run == now

        t2 = s.try_get_item(f1, 1, "t2")
        assert t2 is not None
        assert t2.last_run == now

        t3 = s.try_get_item(f1, 2, "t3")
        assert t3 is not None
        assert t3.last_run <= now

        assert s.try_get_item(f1, 3, "t4") is None

        t1b = s.try_get_item(f1, 0, "t1b")
        assert t1b is not None
        assert t1b.last_run == now

        t2b = s.try_get_item(f1, 1, "t2b")
        assert t2b is not None

        f1_2 = s.try_get_file("abc_2")
        assert f1_2 is not None

        assert s.try_get_item(f1_2, 0, "t1_2") is not None
        assert s.try_get_item(f1_2, 1, "t2_2") is not None

        f2 = s.try_get_file("def")
        if prune:
            assert f2 is None
        else:
            assert f2 is not None
            assert s.try_get_item(f2, 0, "t5") is None
            assert s.try_get_item(f2, 1, "t6") is None

        f3 = s.try_get_file("ghi")
        if prune:
            assert f3 is None
        else:
            assert f3 is not None


def test_drop_all_entries(populated_engine: InMemoryEngine):
    """Test the `Session.drop_all_entries` method."""

    with populated_engine.new_session() as s:
        r = s.drop_all_entries()
        assert r.files_dropped == 3
        assert r.tests_dropped == 6

    engine = populated_engine.get_underlying_engine()
    with Session(engine) as session:
        assert session.query(TestFile).count() == 0
        assert session.query(TestItem).count() == 0
