"""
ledger.py
---------
The ledger is the single source of truth for financial tracking.
It is driven entirely by events — nothing writes to it directly from
game logic.

Design principles
-----------------
- Each settled hand appends an immutable RoundRecord to a list.
- Running totals are kept as simple accumulators alongside; nothing
  is recomputed by scanning the full history.
- Statistics (EV, std-dev, win-rate …) are derived on demand from
  the accumulated records — never stored redundantly mid-simulation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import math
import numpy as np
from events import (
    EventType, HandSettledEvent, RoundEndedEvent,
    PlayerBlackjackEvent, DealerBlackjackEvent, BlackjackPushEvent,
    BetPlacedEvent, Outcome
)


# ---------------------------------------------------------------------------
# Per-round record (immutable once appended)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoundRecord:
    round_number:   int
    wagered:        float   # total money put at risk this round (all hands/doubles)
    net:            float   # net P/L this round (positive = player won)
    bankroll_after: float
    outcomes:       tuple   # tuple of Outcome values, one per settled hand


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

class Ledger:
    """
    Subscribes to financial events; maintains a complete per-round history
    and running summary statistics.
    """

    def __init__(self, starting_bankroll: float):
        self.starting_bankroll: float = starting_bankroll
        self.bankroll:          float = starting_bankroll

        # Per-round history (append-only)
        self._records: List[RoundRecord] = []

        # Running accumulators (updated after each round)
        self._total_wagered: float = 0.0
        self._total_net:     float = 0.0
        self._wins:          int   = 0
        self._losses:        int   = 0
        self._pushes:        int   = 0
        self._blackjacks:    int   = 0

        # Within-round scratch state (reset by on_round_ended)
        self._round_number:   int   = 0
        self._round_wagered:  float = 0.0
        self._round_net:      float = 0.0
        self._round_outcomes: list  = []

    # ------------------------------------------------------------------
    # Event handlers  (called by the engine's event bus)
    # ------------------------------------------------------------------

    def on_event(self, event) -> None:
        t = event.type
        if   t == EventType.BET_PLACED:         self._on_bet(event)
        elif t == EventType.HAND_SETTLED:        self._on_settled(event)
        elif t == EventType.PLAYER_BLACKJACK:    self._on_player_bj(event)
        elif t == EventType.DEALER_BLACKJACK:    self._on_dealer_bj(event)
        elif t == EventType.BLACKJACK_PUSH:      self._on_bj_push(event)
        elif t == EventType.ROUND_STARTED:       self._on_round_started(event)
        elif t == EventType.ROUND_ENDED:         self._on_round_ended(event)
        elif t == EventType.DOUBLE_DOWN:         self._on_double(event)

    def _on_round_started(self, event) -> None:
        self._round_number  = event.round_number
        self._round_wagered = 0.0
        self._round_net     = 0.0
        self._round_outcomes = []

    def _on_bet(self, event: BetPlacedEvent) -> None:
        # Deduct from bankroll; track wagered
        self.bankroll       -= event.amount
        self._round_wagered += event.amount

    def _on_double(self, event) -> None:
        self.bankroll       -= event.extra_bet
        self._round_wagered += event.extra_bet

    def _on_settled(self, event: HandSettledEvent) -> None:
        # Add winnings back to bankroll (net already accounts for bet deduction)
        # net = +bet on win, -bet on loss (bet already deducted), 0 on push
        # For a win: bankroll gets back 2×bet (stake + profit), net = +bet
        # For a push: bankroll gets back 1×bet, net = 0
        # For a loss: bankroll gets nothing back, net = -bet
        if event.outcome == Outcome.WIN:
            self.bankroll += event.bet * 2
        elif event.outcome == Outcome.PUSH:
            self.bankroll += event.bet

        self._round_net += event.net
        self._round_outcomes.append(event.outcome)

        if event.outcome == Outcome.WIN:
            self._wins   += 1
        elif event.outcome == Outcome.LOSS:
            self._losses += 1
        else:
            self._pushes += 1

    def _on_player_bj(self, event: PlayerBlackjackEvent) -> None:
        # Stake already deducted via BET_PLACED; add back stake + 1.5× profit
        self.bankroll    += event.payout        # payout = 2.5 × bet
        self._round_net  += event.payout - event.bet  # net = +1.5×bet
        self._blackjacks += 1
        self._round_outcomes.append(Outcome.BLACKJACK)

    def _on_dealer_bj(self, event: DealerBlackjackEvent) -> None:
        # Stake already deducted via BET_PLACED; nothing returned to bankroll.
        # We still must record the loss in _round_net so total_net is accurate.
        self._round_net -= event.bet
        self._losses    += 1
        self._round_outcomes.append(Outcome.LOSS)

    def _on_bj_push(self, event: BlackjackPushEvent) -> None:
        self.bankroll   += event.bet   # return stake
        self._round_net += 0
        self._pushes    += 1
        self._round_outcomes.append(Outcome.PUSH)

    def _on_round_ended(self, event: RoundEndedEvent) -> None:
        record = RoundRecord(
            round_number   = self._round_number,
            wagered        = self._round_wagered,
            net            = self._round_net,
            bankroll_after = self.bankroll,
            outcomes       = tuple(self._round_outcomes),
        )
        self._records.append(record)
        self._total_wagered += self._round_wagered
        self._total_net     += self._round_net

    # ------------------------------------------------------------------
    # Statistics (computed on demand — no stale cache risk)
    # ------------------------------------------------------------------

    @property
    def rounds_played(self) -> int:
        return len(self._records)

    @property
    def total_wagered(self) -> float:
        return self._total_wagered

    @property
    def total_net(self) -> float:
        return self._total_net

    @property
    def ev(self) -> float:
        """Player edge as a fraction of total wagered (e.g. -0.005 = -0.5%)."""
        return self._total_net / self._total_wagered if self._total_wagered else 0.0

    @property
    def win_rate(self) -> float:
        """Fraction of *individual hands* won (excludes pushes from denominator)."""
        decided = self._wins + self._losses
        return self._wins / decided if decided else 0.0

    @property
    def std_dev(self):
        """Standard deviation of per-round net P/L."""
        if len(self._records) < 2:
            return 0.0
        nets = [r.net for r in self._records]
        return np.std(nets, ddof=1)

    @property
    def records(self) -> List[RoundRecord]:
        return list(self._records)   # defensive copy

    def summary(self) -> dict:
        return {
            'rounds':          self.rounds_played,
            'total_wagered':   round(self._total_wagered, 2),
            'total_net':       round(self._total_net, 2),
            'ev_pct':          round(self.ev * 100, 4),
            'win_rate_pct':    round(self.win_rate * 100, 2),
            'std_dev':         round(self.std_dev, 2),
            'blackjacks':      self._blackjacks,
            'wins':            self._wins,
            'losses':          self._losses,
            'pushes':          self._pushes,
            'final_bankroll':  round(self.bankroll, 2),
        }
