"""
events.py
---------
All simulation events as dataclasses.  The engine fires these in order;
any component (counter, logger, ledger) subscribes to the ones it needs.

Event flow per hand
-------------------
SHOE_SHUFFLED
ROUND_STARTED
  CARD_DEALT  (player card 1)
  CARD_DEALT  (player card 2)
  CARD_DEALT  (dealer upcard)
  CARD_DEALT  (dealer hole – NOT counted until revealed)
  [BLACKJACK_PUSH | DEALER_BLACKJACK | PLAYER_BLACKJACK]
  -- or --
  BET_PLACED  (initial)
  [SPLIT_INITIATED
    BET_PLACED  (second hand)
    CARD_DEALT  × N
    [DOUBLE_DOWN × hand]
    CARD_DEALT  × N  ...]
  [DOUBLE_DOWN
    BET_PLACED  (double)]
  CARD_DEALT  × N   (player hits)
  HOLE_CARD_REVEALED
  CARD_DEALT  × N   (dealer hits)
  HAND_SETTLED  × N
ROUND_ENDED
SHOE_EXHAUSTED
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


# ---------------------------------------------------------------------------
# Card primitives (shared between events and shoe)
# ---------------------------------------------------------------------------

SUITS = ('Hearts', 'Diamonds', 'Clubs', 'Spades')
VALUES = ('2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A')


@dataclass(frozen=True)
class Card:
    suit: str
    value: str

    def __str__(self) -> str:
        return f'{self.value}{"♥" if self.suit=="Hearts" else "♦" if self.suit=="Diamonds" else "♣" if self.suit=="Clubs" else "♠"}'

    @property
    def pip(self) -> int:
        """Numeric value for hand calculation (Ace = 11)."""
        if self.value in ('J', 'Q', 'K'):
            return 10
        if self.value == 'A':
            return 11
        return int(self.value)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(Enum):
    SHOE_SHUFFLED      = auto()
    ROUND_STARTED      = auto()
    BET_PLACED         = auto()
    CARD_DEALT         = auto()
    HOLE_CARD_REVEALED = auto()
    PLAYER_ACTION      = auto()   # hit / stand / double / split
    DOUBLE_DOWN        = auto()
    SPLIT_INITIATED    = auto()
    PLAYER_BLACKJACK   = auto()
    DEALER_BLACKJACK   = auto()
    BLACKJACK_PUSH     = auto()
    HAND_SETTLED       = auto()   # win / loss / push per hand
    ROUND_ENDED        = auto()
    SHOE_EXHAUSTED     = auto()


# ---------------------------------------------------------------------------
# Outcome enum  (used in HAND_SETTLED)
# ---------------------------------------------------------------------------

class Outcome(Enum):
    WIN        = 'win'
    LOSS       = 'loss'
    PUSH       = 'push'
    BLACKJACK  = 'blackjack'   # 3:2 pay


# ---------------------------------------------------------------------------
# Event payload dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ShoeShuffledEvent:
    type: EventType = field(default=EventType.SHOE_SHUFFLED, init=False)
    num_decks: int = 1
    total_cards: int = 52


@dataclass
class RoundStartedEvent:
    type: EventType = field(default=EventType.ROUND_STARTED, init=False)
    round_number: int = 0
    cards_remaining: int = 0
    running_count: float = 0.0
    true_count: float = 0.0
    bankroll: float = 0.0


@dataclass
class BetPlacedEvent:
    type: EventType = field(default=EventType.BET_PLACED, init=False)
    hand_id: int = 0          # 0 = main, 1+ = split hands
    amount: float = 0.0
    bankroll_after: float = 0.0
    reason: str = 'initial'   # 'initial' | 'split' | 'double'


@dataclass
class CardDealtEvent:
    type: EventType = field(default=EventType.CARD_DEALT, init=False)
    card: Card = field(default_factory=lambda: Card('Spades', 'A'))
    recipient: str = 'player'   # 'player' | 'dealer' | f'split_{n}'
    hand_id: int = 0
    face_up: bool = True
    count_update: float = 0.0   # delta applied to running count (0 if hole card)


@dataclass
class HoleCardRevealedEvent:
    type: EventType = field(default=EventType.HOLE_CARD_REVEALED, init=False)
    card: Card = field(default_factory=lambda: Card('Spades', 'A'))
    count_update: float = 0.0


@dataclass
class PlayerActionEvent:
    type: EventType = field(default=EventType.PLAYER_ACTION, init=False)
    hand_id: int = 0
    action: str = 'stand'       # 'hit' | 'stand' | 'double' | 'split'
    hand_value: int = 0
    dealer_upcard: Card = field(default_factory=lambda: Card('Spades', 'A'))


@dataclass
class DoubleDownEvent:
    type: EventType = field(default=EventType.DOUBLE_DOWN, init=False)
    hand_id: int = 0
    extra_bet: float = 0.0
    card: Card = field(default_factory=lambda: Card('Spades', 'A'))
    count_update: float = 0.0


@dataclass
class SplitInitiatedEvent:
    type: EventType = field(default=EventType.SPLIT_INITIATED, init=False)
    original_hand_id: int = 0
    new_hand_ids: List[int] = field(default_factory=list)
    extra_bet: float = 0.0


@dataclass
class PlayerBlackjackEvent:
    type: EventType = field(default=EventType.PLAYER_BLACKJACK, init=False)
    payout: float = 0.0
    bet: float = 0.0


@dataclass
class DealerBlackjackEvent:
    type: EventType = field(default=EventType.DEALER_BLACKJACK, init=False)
    dealer_hand: List[Card] = field(default_factory=list)
    bet: float = 0.0   # player's bet that is lost


@dataclass
class BlackjackPushEvent:
    type: EventType = field(default=EventType.BLACKJACK_PUSH, init=False)
    bet: float = 0.0


@dataclass
class HandSettledEvent:
    type: EventType = field(default=EventType.HAND_SETTLED, init=False)
    hand_id: int = 0
    outcome: Outcome = Outcome.PUSH
    bet: float = 0.0
    net: float = 0.0            # +bet on win, -bet on loss, 0 on push, +1.5×bet on BJ
    player_total: int = 0
    dealer_total: int = 0


@dataclass
class RoundEndedEvent:
    type: EventType = field(default=EventType.ROUND_ENDED, init=False)
    round_number: int = 0
    net_this_round: float = 0.0
    total_wagered_this_round: float = 0.0
    bankroll: float = 0.0


@dataclass
class ShoeExhaustedEvent:
    type: EventType = field(default=EventType.SHOE_EXHAUSTED, init=False)
    rounds_played: int = 0
    cards_dealt: int = 0


# Union type for type checkers
AnyEvent = (
    ShoeShuffledEvent | RoundStartedEvent | BetPlacedEvent | CardDealtEvent |
    HoleCardRevealedEvent | PlayerActionEvent | DoubleDownEvent |
    SplitInitiatedEvent | PlayerBlackjackEvent | DealerBlackjackEvent |
    BlackjackPushEvent | HandSettledEvent | RoundEndedEvent | ShoeExhaustedEvent
)
