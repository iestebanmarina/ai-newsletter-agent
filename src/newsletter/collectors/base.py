from abc import ABC, abstractmethod

from ..models import Article


class BaseCollector(ABC):
    """Base interface for all content collectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this collector."""
        ...

    @abstractmethod
    def collect(self) -> list[Article]:
        """Collect articles from this source. Returns a list of Article objects."""
        ...
