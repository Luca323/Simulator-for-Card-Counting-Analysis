"""
strategy.py
-----------
All playing strategies (basic strategy) and betting strategies as pure,
stateless functions.  Nothing here mutates game state.

Playing strategy signature:
    fn(upcard: Card, hand_value: int, pair: bool, soft: bool) -> str
    Returns one of: 'hit' | 'stand' | 'double' | 'split'

Betting strategy signature:
    fn(true_count: float) -> float
    Returns the bet amount in units.
"""

from __future__ import annotations
from events import Card


# ===========================================================================
# Betting strategies
# ===========================================================================

def flat(_: float, unit: float = 10.0) -> float:
    """Flat bet — ignores the count."""
    return unit


def hi_lo_betting(true_count: float, unit: float = 10.0) -> float:
    """Conservative ramp: 1× below TC+2, scales to 8× at TC+8."""
    if true_count >= 2:
        return unit * min(int(true_count), 8)
    return unit


def conservative_counting(true_count: float, unit: float = 10.0) -> float:
    """Spread 1-4×: low heat, modest edge."""
    if true_count >= 3:
        return unit * 4
    if true_count >= 2:
        return unit * 3
    if true_count >= 1:
        return unit * 2
    return unit

def balanced_counting(true_count: float, unit: float = 10.0) -> float:
    # spread 1 - 10 => middle road
    if true_count >= 5:
        return unit * 10
    if true_count >= 4:
        return unit * 8
    if true_count >= 3:
        return unit * 6
    if true_count >= 2:
        return unit * 4
    if true_count >= 1:
        return unit * 2
    return unit

def aggressive_counting(true_count: float, unit: float = 10.0) -> float:
    """Spread 1-12×: high edge, high variance."""
    if true_count >= 4:
        return unit * 12
    if true_count >= 3:
        return unit * 8
    if true_count >= 2:
        return unit * 4
    if true_count >= 1:
        return unit * 2
    return unit


def half_kelly_betting(true_count: float, unit: float = 10.0) -> float:
    """
    Half-Kelly sizing off a fixed bankroll anchor.

    edge ≈ (true_count × 0.005) - house_edge_at_zero
    bet  = (edge / variance) × bankroll × kelly_fraction

    Variance for blackjack ≈ 1.15 (accounts for splits, doubles, BJ)
    Kelly fraction = 0.5 (half Kelly)
    """
    starting_bankroll = 1000.0
    house_edge_at_zero = 0.005
    VARIANCE = 1.15
    KELLY_FRAC = 0.5
    TC_EDGE_SLOPE = 0.005  # ~0.5% per true count point

    edge = (true_count * TC_EDGE_SLOPE) - house_edge_at_zero

    if edge <= 0:
        return unit  # minimum bet when house has edge

    full_kelly = edge / VARIANCE
    bet = starting_bankroll * full_kelly * KELLY_FRAC

    # Floor at 1 unit, cap at a sensible table maximum
    return max(unit, min(bet, unit * 20))


def kelly(true_count: float, bankroll: float = 1000.0, unit: float = 10.0) -> float:
    """Kelly Criterion: bet fraction proportional to estimated edge."""
    if true_count >= 1:
        advantage  = true_count * 0.005
        kelly_bet  = bankroll * advantage
        return max(unit, min(kelly_bet, unit * 10))
    return unit


# ===========================================================================
# Basic playing strategy
# ===========================================================================

# ---------------------------------------------------------------------------
# Internal lookup tables
# ---------------------------------------------------------------------------

# Pair splitting table.
# Keys are the *hand value* for most pairs.
# A,A is stored as key 22 to avoid collision with 6,6 (also value 12).
# Values: 'P' = always split; dict[dealer_upcard_int → 'P'] = conditional split.
_PAIR: dict[int, object] = {
    4:  {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P'},          # 2,2 vs 2-7
    6:  {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P'},          # 3,3 vs 2-7
    8:  {5:'P', 6:'P'},                                        # 4,4 vs 5-6
    # 5,5 → never split (falls through to hard table as value 10)
    12: {2:'P', 3:'P', 4:'P', 5:'P', 6:'P'},                 # 6,6 vs 2-6
    14: {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 7:'P'},          # 7,7 vs 2-7
    16: 'P',                                                   # 8,8 always
    18: {2:'P', 3:'P', 4:'P', 5:'P', 6:'P', 8:'P', 9:'P'},  # 9,9 vs 2-9 ex 7
    20: 'S',                                                   # 10,10 never
    22: 'P',                                                   # A,A always (sentinel key)
}

# Hard totals (no pair, no soft).
# Values: str = always that action; dict[dealer_val → action] = conditional.
_HARD: dict[int, object] = {
    4:'H', 5:'H', 6:'H', 7:'H', 8:'H',
    9:  {3:'D', 4:'D', 5:'D', 6:'D'},
    10: {2:'D', 3:'D', 4:'D', 5:'D', 6:'D', 7:'D', 8:'D', 9:'D'},
    11: {2:'D', 3:'D', 4:'D', 5:'D', 6:'D', 7:'D', 8:'D', 9:'D', 10:'D', 11:'D'},
    12: {4:'S', 5:'S', 6:'S'},
    13: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S'},
    14: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S'},
    15: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S'},
    16: {2:'S', 3:'S', 4:'S', 5:'S', 6:'S'},
    17:'S', 18:'S', 19:'S', 20:'S', 21:'S',
}

# Soft totals (hand contains an Ace counted as 11).
# A,2 = soft 13, A,3 = soft 14, …, A,9 = soft 20, A,10/BJ = soft 21.
_SOFT: dict[int, object] = {
    13: {2:'H', 3:'H', 4:'H', 5:'H', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 11:'H'},
    14: {2:'H', 3:'H', 4:'H', 5:'H', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 11:'H'},
    15: {2:'H', 3:'H', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 11:'H'},
    16: {2:'H', 3:'H', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 11:'H'},
    17: {2:'H', 3:'D', 4:'D', 5:'D', 6:'D', 7:'H', 8:'H', 9:'H', 10:'H', 11:'H'},
    18: {2:'S', 3:'D', 4:'D', 5:'D', 6:'D', 7:'S', 8:'S', 9:'H', 10:'H', 11:'H'},
    19: 'S',
    20: 'S',
    21: 'S',
}

_ACTION = {'H': 'hit', 'S': 'stand', 'D': 'double', 'P': 'split'}


def _dealer_int(upcard: Card) -> int:
    """Normalise dealer upcard to integer for table lookup."""
    if upcard.value in ('J', 'Q', 'K'):
        return 10
    if upcard.value == 'A':
        return 11
    return int(upcard.value)


def _lookup(table: dict, hand_val: int, d_val: int) -> str:
    row = table.get(hand_val, 'H')
    if isinstance(row, dict):
        return _ACTION[row.get(d_val, 'H')]
    return _ACTION[row]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def basic(upcard: Card, hv: int, pair: bool, soft: bool) -> str:
    """
    Return the basic-strategy action for the given situation.

    Parameters
    ----------
    upcard : dealer's face-up card
    hv     : best hand value (Ace counted optimally)
    pair   : True when the two-card hand is a splittable pair
    soft   : True when an Ace is being counted as 11
    """
    d = _dealer_int(upcard)

    # A,A: soft=True AND pair=True — must go to pair table (key 22), not soft table
    if pair and soft and hv == 12:
        return _lookup(_PAIR, 22, d)

    # All other pairs (not A,A): route to pair table
    if pair:
        if hv in _PAIR:
            return _lookup(_PAIR, hv, d)
        # e.g. 5,5 — not in pair table, fall through to hard
        return _lookup(_HARD, hv, d)

    if soft:
        return _lookup(_SOFT, hv, d)

    return _lookup(_HARD, hv, d)
