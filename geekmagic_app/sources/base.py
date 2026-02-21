"""
base.py - Abstract base class for all data sources.

Every source plugin must implement these three methods:
    fetch()     → pulls raw data from wherever (HTTP, file, socket, etc.)
    parse(raw)  → converts raw data into a list of DataItem dicts
    get_items() → convenience: fetch + parse in one call

The separation between fetch and parse matters:
    - It makes unit testing easy (you can test parse() with canned data)
    - It makes error handling granular (network error vs parse error)
    - Future sources (RSS, IMAP) follow the exact same contract
"""

from abc import ABC, abstractmethod
from geekmagic_app.models.data_item import DataItem


class DataSource(ABC):

    @abstractmethod
    def fetch(self) -> object:
        """
        Pull raw data from the source.
        Return type depends on the source (str, bytes, dict, etc.)
        Should raise an exception on network/IO failure.
        """
        ...

    @abstractmethod
    def parse(self, raw: object) -> list[DataItem]:
        """
        Convert raw data into a list of DataItems.
        Should never raise — return an empty list on parse failure.
        """
        ...

    def get_items(self) -> list[DataItem]:
        """Fetch and parse in one call. Propagates fetch exceptions."""
        raw = self.fetch()
        return self.parse(raw)
