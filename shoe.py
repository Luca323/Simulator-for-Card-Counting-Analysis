"""
shoe.py
-------
Pure shoe / card primitives.  No game logic lives here.
"""

from __future__ import annotations
from random import shuffle as _shuffle
from events import Card, SUITS, VALUES


def _build_deck() -> list[Card]:
    return [Card(suit, value) for suit in SUITS for value in VALUES]


class Shoe:
    """
    A multi-deck shoe.  Immutable configuration; mutable card list.
    Cards are dealt from the END of the list (pop) for O(1) performance.
    """

    def __init__(self, num_decks: int = 6):
        self.num_decks = num_decks
        self._cards: list[Card] = []
        self._initial_size: int = 0
        self._rebuild()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self._cards = _build_deck() * self.num_decks
        self._initial_size = len(self._cards)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def shuffle(self) -> None:
        """Rebuild from scratch and shuffle — guarantees a full shoe."""
        self._rebuild()
        _shuffle(self._cards)

    def deal(self) -> Card:
        if not self._cards:
            raise RuntimeError("Shoe is empty")
        return self._cards.pop()

    # ------------------------------------------------------------------
    # Penetration / state queries
    # ------------------------------------------------------------------

    @property
    def cards_remaining(self) -> int:
        return len(self._cards)

    @property
    def cards_dealt(self) -> int:
        return self._initial_size - len(self._cards)

    @property
    def decks_remaining(self) -> float:
        return len(self._cards) / 52.0

    def past_cut_card(self, penetration: float = 0.75) -> bool:
        """True once the fraction *dealt* exceeds penetration."""
        return self.cards_dealt / self._initial_size >= penetration

    def __len__(self) -> int:
        return self.cards_remaining

    def __repr__(self) -> str:
        return (f"Shoe(num_decks={self.num_decks}, "
                f"remaining={self.cards_remaining}/{self._initial_size})")
