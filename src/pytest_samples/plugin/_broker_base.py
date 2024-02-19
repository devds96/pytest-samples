import logging as _logging
import pytest as _pytest
import random as _random
import time as _time

from abc import ABC as _ABC
from arrow import Arrow as _Arrow
from datetime import timedelta as _timedelta
from pytest import Item as _Item
from typing import List as _List, Optional as _Optional

from . import _meta


_logger = _logging.getLogger(__name__)
"""The logger for this module."""


_skip_marker = _pytest.mark.skip(
    reason=f"{_meta.PLUGIN_FULL_NAME} timeout expired"
)
"""The marker to add to an item that should be skipped due to the soft
timeout.
"""


class SamplesBrokerBase(_ABC):
    """The base class for broker classes dermining which samples to
    execute and in which order.
    """

    __slots__ = (
        "_soft_timeout",
        "_seed",
        "_rng",
        "_start_time",
        "_past_timeout"
    )

    def __init__(
        self, soft_timeout: _Optional[_timedelta], seed: _Optional[str]
    ) -> None:
        """Initialize a `SamplesBrokerBase`.

        Args:
            soft_timeout (Optional[timedelta]): The time after which the
                timeout should occur or None, to disable it.
            seed (Optional[str]): The seed to use for the RNG or None
                to use a time based seed.
        """

        self._soft_timeout = soft_timeout
        """Stores the soft timeout timedelta."""

        if seed is None:
            _logger.info("No seed provided. Using Epoch.")
            seed = str(_time.time_ns())
        _logger.info(
            "The RNG seed is %r of type %r.",
            seed,
            type(seed).__qualname__
        )

        self._seed = seed
        """The seed for the RNG."""

        self._rng = _random.Random(seed)
        """The RNG to use for random processes."""

        self._start_time: _Optional[_Arrow] = None
        """Stores the start time of the test loop. May be unset if there
        were no tests.
        """
        self._past_timeout: bool = False
        """Whether the timeout time has been reached."""

    def _shuffle_items(self, items: _List[_Item]) -> None:
        """Shuffle a list of items.

        Args:
            items (List[Item]): The item list to shuffle.
        """
        self._rng.shuffle(items)

    @classmethod
    def _mark_skip(cls, item: _Item) -> None:
        """Mark an item as "to be skipped".

        Args:
            item (Item): The item to mark.
        """
        item.add_marker(_skip_marker)

    def pytest_runtest_protocol(self, item: _Item) -> None:
        """Pytest hook called in the test loop to test an item.

        Args:
            item (Item): The item to test.
        """
        self._prepare_item_check_timeout(item)

    def _prepare_item_check_timeout(self, item: _Item) -> None:
        """Called to prepare an item for the test and check if the
        timeout has expired.

        Args:
            item (Item): The item to test.
        """
        timeout = self._soft_timeout
        if timeout is None:
            return
        if self._past_timeout:
            self._mark_skip(item)
            return
        st = self._start_time
        if st is None:
            # This will be set before the first test is run.
            self._start_time = _Arrow.now()
            _logger.info("Setting start time at %s.", self._start_time)
            return
        if self.check_timeout_expired(st, timeout):
            _logger.info("Timeout after %s.", timeout)
            self._past_timeout = True
            self._mark_skip(item)

    @classmethod
    def check_timeout_expired(
        cls, start_time: _Arrow, timeout: _timedelta
    ) -> bool:
        """Check if the timeout has expired given the start time and the
        timeout `timedelta`.

        Args:
            start_time (Arrow): The start time.
            timeout (_timedelta): The timedelta after which the timeout
                should occur.

        Returns:
            bool: Whether the timeout has expired.
        """
        return (_Arrow.now() - start_time) >= timeout
