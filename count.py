"""
count.py
--------
All card-counting systems as pure, stateless functions.
Each takes a Card and returns a numeric delta to apply to the running count.

Counter state (running_count, true_count) lives in the engine, not here.
"""

from __future__ import annotations
from events import Card


# ---------------------------------------------------------------------------
# Count-value functions  (Card → delta)
# ---------------------------------------------------------------------------

def hi_lo(card: Card) -> float:
    """Hi-Lo (balanced): +1 / 0 / -1."""
    if card.value in ('2', '3', '4', '5', '6'):
        return 1
    if card.value in ('7', '8', '9'):
        return 0
    return -1  # 10, J, Q, K, A


def omega_2(card: Card) -> float:
    """Omega II (balanced, multi-level)."""
    if card.value in ('2', '3', '7'):
        return 1
    if card.value in ('4', '5', '6'):
        return 2
    if card.value in ('8', 'A'):
        return 0
    if card.value == '9':
        return -1
    return -2  # 10, J, Q, K


def ten_count(card: Card) -> float:
    """Thorp's original Ten-Count (unbalanced)."""
    if card.value in ('2', '3', '4', '5', '6', '7', '8', '9'):
        return 4
    return -9  # 10, J, Q, K, A


def zen_count(card: Card) -> float:
    """Zen Count (balanced, multi-level)."""
    if card.value in ('2', '3', '7'):
        return 1
    if card.value in ('4', '5', '6'):
        return 2
    if card.value in ('8', '9'):
        return 0
    if card.value == 'A':
        return -1
    return -2  # 10, J, Q, K


def point_count(card: Card) -> float:
    """Point Count (unbalanced — start offset = -2 × num_decks)."""
    if card.value in ('3', '4', '5', '6'):
        return 1
    if card.value in ('2', '7', '8', '9'):
        return 0
    return -1  # 10, J, Q, K, A


def complete_point_count(card: Card) -> float:
    """Thorp Complete Point Count — same deltas as Hi-Lo; true-count
    formula differs and is handled in the engine."""
    if card.value in ('2', '3', '4', '5', '6'):
        return 1
    if card.value in ('7', '8', '9'):
        return 0
    return -1


def wong_halves(card: Card) -> float:
    """Wong Halves (balanced, fractional)."""
    if card.value == '5':
        return 1.5
    if card.value in ('3', '4', '6'):
        return 1.0
    if card.value in ('2', '7'):
        return 0.5
    if card.value == '8':
        return 0.0
    if card.value == 'A':
        return -1.0
    if card.value == '9':
        return -0.5
    return -1.0  # 10, J, Q, K


# ---------------------------------------------------------------------------
# Registry  (name → function)
# ---------------------------------------------------------------------------

SYSTEMS: dict[str, object] = {
    'hi-lo':                 hi_lo,
    'omega-2':               omega_2,
    'ten-count':             ten_count,
    'zen-count':             zen_count,
    'point-count':           point_count,
    'complete-point-count':  complete_point_count,
    'wong-halves':           wong_halves,
}

# Unbalanced systems need a starting offset of (initial_offset_per_deck × num_decks)
INITIAL_OFFSET_PER_DECK: dict[str, float] = {
    'point-count': -2.0,
    'ten-count':    0.0,   # starts at 0 but tracks differently
}


class CounterState:
    """
    Mutable counter that lives for one shoe.
    Separating state from function keeps the counting functions pure
    while still providing a convenient stateful interface to the engine.
    """

    def __init__(self, system: str, num_decks: int, shoe_total_cards: int):
        system = system.lower()
        if system not in SYSTEMS:
            raise ValueError(f"Unknown counting system '{system}'. "
                             f"Choose from: {list(SYSTEMS)}")
        self.system         = system
        self._fn            = SYSTEMS[system]
        self.num_decks      = num_decks
        self.shoe_total     = shoe_total_cards
        self.running_count: float = INITIAL_OFFSET_PER_DECK.get(system, 0.0) * num_decks
        self.true_count:    float = 0.0
        self._cards_seen:   int   = 0   # used only by complete-point-count

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def observe(self, card: Card) -> float:
        """
        Apply one card to the running count.
        Returns the delta so callers can embed it in events.
        """
        delta = self._fn(card)
        self.running_count += delta
        self._cards_seen   += 1
        return delta

    def update_true_count(self, decks_remaining: float) -> float:
        """Recalculate true count given current decks remaining."""
        if self.system == 'complete-point-count':
            cards_remaining = self.shoe_total - self._cards_seen
            self.true_count = self.running_count - (cards_remaining / 52.0)
        elif decks_remaining > 0:
            import math
            self.true_count = math.floor(self.running_count / decks_remaining)
        else:
            self.true_count = self.running_count
        return self.true_count

    def reset(self) -> None:
        """Reset for a new shoe."""
        self.running_count = INITIAL_OFFSET_PER_DECK.get(self.system, 0.0) * self.num_decks
        self.true_count    = 0.0
        self._cards_seen   = 0
