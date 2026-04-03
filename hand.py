"""
hand.py
-------
Pure functions for hand-value arithmetic.
All functions are stateless — they take a list of Cards and return a value.
"""

from __future__ import annotations
from events import Card


def hand_value(cards: list[Card]) -> int:
    """Best non-busting total; converts Ace 11→1 as needed."""
    total = sum(c.pip for c in cards)
    aces  = sum(1 for c in cards if c.value == 'A')
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def is_soft(cards: list[Card]) -> bool:
    """True when at least one Ace is counted as 11."""
    if not any(c.value == 'A' for c in cards):
        return False
    hard = sum(1 if c.value == 'A' else c.pip for c in cards)
    return hard + 10 <= 21


def is_pair(cards: list[Card]) -> bool:
    """True when exactly 2 cards of equal rank (face cards normalised to 10)."""
    if len(cards) != 2:
        return False
    def rank(c: Card) -> str:
        return '10' if c.value in ('J', 'Q', 'K') else c.value
    return rank(cards[0]) == rank(cards[1])


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


def is_busted(cards: list[Card]) -> bool:
    return hand_value(cards) > 21
