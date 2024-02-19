import pytest

from typing import List

from pytest_samples.tools._collectiontools import move_idx_to_end


class TestMoveIdxToEnd:
    """Tests for the `move_idx_to_end` function."""

    class TestsNoReodering:
        """Groups tests that do not use a reordering key for the shifted
        elements.
        """

        def test_regular_example(self):
            """Test a simple example."""
            src = [0, 1, 2, 3, 4, 5]
            idx = {0, 2, 5}
            move_idx_to_end(src, idx)
            assert src == [1, 3, 4, 0, 2, 5]

        def test_idx_out_of_bounds(self):
            """Test a simple example with an out-of-bounds index."""
            src = [0, 1, 2, 3, 4, 5]
            idx = (0, 1, 2, 3, 100)
            with pytest.raises(IndexError):
                move_idx_to_end(src, idx)

        def test_idx_negative(self):
            """Test that negative indices lead to an `IndexError`."""
            src = [0, 1, 2, 3, 4, 5]
            idx = (0, -1, 3)
            with pytest.raises(IndexError, match=".*negative.*"):
                move_idx_to_end(src, idx)

        def test_empty_idx(self):
            """Test for correct behavior in case 'idx' is empty."""
            src = [0, 1, 2, 3, 4, 5]
            idx: List[int] = []
            move_idx_to_end(src, idx)

        def test_non_unique_idx(self):
            """Test that a `ValueError` is raised in case of non-unique
            indices.
            """
            src = [0, 1, 2, 3, 4, 5]
            idx = [0, 1, 2, 2, 5]
            with pytest.raises(ValueError, match=".*duplicate.*"):
                move_idx_to_end(src, idx)

    class TestsReodering:
        """Groups tests that use a reordering key to reorder the shifted
        elements.
        """

        def test_regular_example_flipped(self):
            """Test a simple example. The elements should now be sorted
            in reverse according to their value.
            """
            src = [0, 1, 2, 3, 4, 5]
            idx = {0, 2, 5}
            move_idx_to_end(src, idx, sorting_key=lambda x: -x)
            assert src == [1, 3, 4, 5, 2, 0]
