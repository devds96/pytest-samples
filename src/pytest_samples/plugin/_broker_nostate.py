from pytest import hookimpl as _hookimpl, Item as _Item
from typing import List as _List

from ._broker_base import SamplesBrokerBase as _SamplesBrokerBase


class NoStateSamplesBroker(_SamplesBrokerBase):

    @_hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, items: _List[_Item]) -> None:
        """The function called for the pytest "collection_modifyitems"
        hook.

        Args:
            items (List[Item]): The list of collected items.
        """
        self._shuffle_items(items)
