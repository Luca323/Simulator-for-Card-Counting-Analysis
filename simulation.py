"""
simulation.py
-------------
High-level simulation runner.  Wires together:
    Shoe → CounterState → Engine → EventBus → Ledger

Usage
-----
    from simulation import SimConfig, run_simulation, run_monte_carlo
    from strategy import basic, aggressive_counting
    from count import SYSTEMS

    # Single shoe
    cfg     = SimConfig(num_decks=6, counting_system='hi-lo',
                        betting_strategy=aggressive_counting)
    ledger  = run_simulation(cfg)
    print(ledger.summary())

    # Monte Carlo: 10 000 shoes
    results = run_monte_carlo(cfg, n=10_000)
    results.print_report()
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from itertools import product
import numpy as np
import matplotlib.pyplot as plt
from events import EventType, RoundEndedEvent
from shoe import Shoe
from count import CounterState, SYSTEMS
from ledger import Ledger
from engine import Engine, EventBus
from strategy import basic, flat, half_kelly_betting, balanced_counting, aggressive_counting, conservative_counting


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class SimConfig:
    """All knobs for one simulation run."""
    num_decks:        int      = 6
    penetration:      float    = 0.75
    counting_system:  str      = 'hi-lo'
    playing_strategy: Callable = field(default=basic)
    betting_strategy: Callable = field(default=flat)
    starting_bankroll: float   = 1000.0
    verbose:          bool     = False


# ---------------------------------------------------------------------------
# Single-shoe simulation
# ---------------------------------------------------------------------------

def run_simulation(cfg: SimConfig) -> Ledger:
    """
    Play one shoe according to cfg.
    Returns a fully-populated Ledger.
    """
    shoe    = Shoe(cfg.num_decks)
    counter = CounterState(cfg.counting_system, cfg.num_decks, shoe.num_decks * 52)
    ledger  = Ledger(cfg.starting_bankroll)
    bus     = EventBus()

    # Subscribe ledger first so financials are always up to date
    bus.subscribe(ledger.on_event)

    # Optional verbose logger
    if cfg.verbose:
        bus.subscribe(_make_verbose_logger())

    engine = Engine(
        shoe              = shoe,
        playing_strategy  = cfg.playing_strategy,
        betting_strategy  = cfg.betting_strategy,
        counter           = counter,
        bus               = bus,
        starting_bankroll = cfg.starting_bankroll,
        penetration       = cfg.penetration,
    )
    engine.run()
    return ledger


# ---------------------------------------------------------------------------
# Monte Carlo runner
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResults:
    cfg:                  SimConfig
    n:                    int       # valid shoes counted
    ev_pct:               float     # aggregate EV = total_net / total_wagered
    std_dev:              float     # std-dev of per-shoe net P/L in units
    se_pct:               float     # standard error on EV in percent (delta method)
    win_rate:             float     # fraction of decided hands won
    avg_wagered_per_shoe: float
    avg_net_per_shoe:     float
    per_shoe_nets:        List[float]   # one net P/L entry per shoe

    def print_report(self) -> None:
        sep = "─" * 60
        print(sep)
        print(f"  Monte Carlo Simulation  ({self.n:,} shoes × {self.cfg.num_decks} decks)")
        print(sep)
        print(f"  Counting system   : {self.cfg.counting_system}")
        print(f"  Penetration       : {self.cfg.penetration:.0%}")
        print(f"  Starting bankroll : {self.cfg.starting_bankroll:,.0f}")
        print(sep)
        print(f"  Player EV         : {self.ev_pct:+.3f}%")
        print(f"  Std-dev (net/shoe): {self.std_dev:,.2f} units")
        print(f"  Win rate          : {self.win_rate:.2%}")
        print(f"  Avg wagered/shoe  : {self.avg_wagered_per_shoe:,.1f}")
        print(f"  Avg net/shoe      : {self.avg_net_per_shoe:+,.2f}")
        print(f"  95% CI on EV      : [{self.ev_pct - 1.96*self.se_pct:+.3f}%,  "
              f"{self.ev_pct + 1.96*self.se_pct:+.3f}%]")
        print(sep)


def run_monte_carlo(cfg: SimConfig, n: int = 10_000) -> MonteCarloResults:
    """
    Run n independent shoes and aggregate statistics.

    EV is computed as total_net / total_wagered across ALL shoes combined
    rather than the mean of per-shoe EVs.  This weights each hand equally
    instead of each shoe equally — a 5-hand shoe and a 50-hand shoe no
    longer count the same toward the final number.

    The confidence interval uses the delta method, which correctly accounts
    for variance in both the numerator (net) and denominator (wagered).
    """
    total_net     = 0.0
    total_wagered = 0.0
    all_nets:     List[float] = []
    all_wagereds: List[float] = []
    win_rates:    List[float] = []

    for _ in range(n):
        ledger = run_simulation(cfg)
        s      = ledger.summary()
        if s['total_wagered'] > 0:
            total_net     += s['total_net']
            total_wagered += s['total_wagered']
            all_nets.append(s['total_net'])
            all_wagereds.append(s['total_wagered'])
            win_rates.append(s['win_rate_pct'])

    valid_n      = len(all_nets)
    aggregate_ev = (total_net / total_wagered) if total_wagered else 0.0

    arr_nets     = np.array(all_nets)
    arr_wagereds = np.array(all_wagereds)

    mean_wagered = float(np.mean(arr_wagereds))
    var_net      = float(np.var(arr_nets,     ddof=1))
    var_wagered  = float(np.var(arr_wagereds, ddof=1))
    cov          = float(np.cov(arr_nets, arr_wagereds, ddof=1)[0, 1])

    # Delta method: SE of the ratio estimator net/wagered
    se = (1 / mean_wagered) * math.sqrt(
        var_net
        + aggregate_ev**2 * var_wagered
        - 2 * aggregate_ev * cov
    ) / math.sqrt(valid_n)

    return MonteCarloResults(
        cfg                  = cfg,
        n                    = valid_n,
        ev_pct               = aggregate_ev * 100,
        std_dev              = float(np.std(arr_nets, ddof=1)),
        se_pct               = se * 100,
        win_rate             = float(np.mean(win_rates)) / 100,
        avg_wagered_per_shoe = mean_wagered,
        avg_net_per_shoe     = float(np.mean(arr_nets)),
        per_shoe_nets        = all_nets
    )


# ---------------------------------------------------------------------------
# Verbose event logger  (subscribes to bus, prints human-readable output)
# ---------------------------------------------------------------------------

def _make_verbose_logger():
    """Returns a subscriber function that pretty-prints every event."""
    def log(event) -> None:
        t = event.type
        if t == EventType.ROUND_STARTED:
            print(f"\n{'='*50}")
            print(f"  Round {event.round_number:>4}  |  "
                  f"Cards left: {event.cards_remaining:>3}  |  "
                  f"RC: {event.running_count:+.1f}  TC: {event.true_count:+.1f}  |  "
                  f"Bank: {event.bankroll:.0f}")
        elif t == EventType.BET_PLACED:
            label = {'initial':'Bet','split':'Split bet','double':'Dbl bet'}.get(event.reason, 'Bet')
            print(f"  {label}: {event.amount:.0f}  (bank→{event.bankroll_after:.0f})")
        elif t == EventType.CARD_DEALT:
            who = event.recipient.replace('_',' ')
            face = str(event.card) if event.face_up else '[hole]'
            print(f"  Deal {face} → {who}")
        elif t == EventType.HOLE_CARD_REVEALED:
            print(f"  Hole card revealed: {event.card}  (Δcount {event.count_update:+.1f})")
        elif t == EventType.PLAYER_ACTION:
            print(f"  Hand {event.hand_id}: {event.action.upper()}"
                  f"  (total={event.hand_value})")
        elif t == EventType.DOUBLE_DOWN:
            print(f"  Double down hand {event.hand_id}  extra bet: {event.extra_bet:.0f}")
        elif t == EventType.SPLIT_INITIATED:
            print(f"  SPLIT → hands {event.new_hand_ids}")
        elif t == EventType.PLAYER_BLACKJACK:
            print(f"  ★ PLAYER BLACKJACK  payout: {event.payout:.1f}")
        elif t == EventType.DEALER_BLACKJACK:
            print(f"  ✗ DEALER BLACKJACK")
        elif t == EventType.BLACKJACK_PUSH:
            print(f"  ↔ BLACKJACK PUSH")
        elif t == EventType.HAND_SETTLED:
            sym = {'win':'✓','loss':'✗','push':'↔','blackjack':'★'}.get(event.outcome.value,'?')
            print(f"  {sym} Hand {event.hand_id}: "
                  f"{event.player_total} vs dealer {event.dealer_total}  "
                  f"net: {event.net:+.0f}")
        elif t == EventType.ROUND_ENDED:
            print(f"  → Round net: {event.net_this_round:+.1f}  "
                  f"bank: {event.bankroll:.0f}")
        elif t == EventType.SHOE_EXHAUSTED:
            print(f"\n{'='*50}")
            print(f"  Shoe exhausted — {event.rounds_played} rounds, "
                  f"{event.cards_dealt} cards dealt")
    return log

def full_sensitivity_simulation():
    penetrations = [0.6, 0.75, 0.9]
    bet_spreads = [aggressive_counting, conservative_counting, balanced_counting]
    deck_sizes = [1, 4, 6]

    for p, s, d in product(penetrations, bet_spreads, deck_sizes):
        systems_to_test = [
            ('Flat (baseline)', 'hi-lo', flat),
            ('Hi-Lo conserv.', 'hi-lo', s),
            ('Hi-Lo aggressive', 'hi-lo', s),
            ('Omega II', 'omega-2', s),
            ('Zen Count', 'zen-count', s),
            ('Wong Halves', 'wong-halves', s),
            ('Complete PC', 'complete-point-count', s),
            ('Point Count', 'point-count', s),
        ]

        num_simulations = int(600_000 / d) #normalize deck sizes

        print(f"{'System':<24} {'EV':>8} {'95% CI':>20} {'Win%':>8} {'Avg Wager':>12}     {'P/L Variance':>12}")
        print("─" * 94)

        for name, system, bet_fn in systems_to_test:
            r = run_monte_carlo(SimConfig(
                num_decks=d,
                counting_system=system,
                betting_strategy=bet_fn,
                starting_bankroll=1000,
                penetration=p
            ), n=num_simulations)
            se = r.std_dev / math.sqrt(r.n)
            ci = f"[{r.ev_pct - 1.96 * se:+.3f}, {r.ev_pct + 1.96 * se:+.3f}]"
            print(f"{name:<24} {r.ev_pct:>+7.3f}%  {ci:>20}  "
                  f"{r.win_rate:>7.2%}  {r.avg_wagered_per_shoe:>11,.0f}     {r.std_dev ** 2:>7.3f}")



if __name__ == '__main__':

    '''# -----------------------------------------------------------------------
    # 1. Verbose single shoe to inspect event flow
    # -----------------------------------------------------------------------
    print("DEMO 1: Verbose single shoe (Hi-Lo / conservative betting)")
    print("─" * 60)
    cfg_verbose = SimConfig(
        num_decks        = 6,
        counting_system  = 'hi-lo',
        betting_strategy = conservative_counting,
        starting_bankroll= 500,
        verbose          = True,
    )
    ledger = run_simulation(cfg_verbose)
    s = ledger.summary()
    print(f"\n  Final summary: {s}")

    # -----------------------------------------------------------------------
    # 2. Monte Carlo: flat betting baseline  (should land near -0.5%)
    # -----------------------------------------------------------------------
    print("\nDEMO 2: Flat betting baseline  (10 000 shoes)")
    run_monte_carlo(SimConfig(
        num_decks        = 6,
        counting_system  = 'hi-lo',
        betting_strategy = flat,
        starting_bankroll= 1000,
    ), n=10_000).print_report()

    # -----------------------------------------------------------------------
    # 3. Monte Carlo: Wong Halves + aggressive spread
    # -----------------------------------------------------------------------
    print("\nDEMO 3: Wong Halves + aggressive betting  (10 000 shoes)")
    results = run_monte_carlo(SimConfig(
        num_decks        = 6,
        counting_system  = 'wong-halves',
        betting_strategy = aggressive_counting,
        starting_bankroll= 1000,
    ), n=10_000)
    results.print_report()

    # -----------------------------------------------------------------------
    # 4. Histogram of per-shoe EV
    # -----------------------------------------------------------------------
    evs = results.per_shoe_evs
    plt.figure(figsize=(10, 5))
    plt.hist(evs, bins=40, color='#2a6496', edgecolor='white', linewidth=0.4)
    plt.axvline(results.ev_pct, color='#e74c3c', linewidth=2,
                label=f'Mean EV: {results.ev_pct:+.3f}%')
    plt.title('Distribution of Player EV per Shoe — Wong Halves / Aggressive')
    plt.xlabel('EV (%)')
    plt.ylabel('Shoes')
    plt.legend()
    plt.tight_layout()
    plt.show()
'''
    # -----------------------------------------------------------------------
    # 5. System comparison table
    # -----------------------------------------------------------------------
    print("\nAll counting systems — 5 000 000 shoes each")
    print(f"{'System':<24} {'EV':>8} {'95% CI':>20} {'Win%':>8} {'Avg Wager':>12}     {'P/L Variance':>12}")
    print("─" * 94)

    systems_to_test = [
        ('Flat (baseline)',     'hi-lo',               flat),
        ('Hi-Lo',    'hi-lo',               balanced_counting),
        ('Omega II',            'omega-2',             balanced_counting),
        ('Zen Count',           'zen-count',           balanced_counting),
        ('Wong Halves',         'wong-halves',         balanced_counting),
        ('Complete PC',         'complete-point-count',balanced_counting),
        ('Point Count',         'point-count',         balanced_counting),
    ]

    for name, system, bet_fn in systems_to_test:
        r = run_monte_carlo(SimConfig(
            num_decks        = 6,
            counting_system  = system,
            betting_strategy = bet_fn,
            starting_bankroll= 2000,
            penetration=0.75
        ), n=600000)
        se = r.std_dev / math.sqrt(r.n)
        ci = f"[{r.ev_pct-1.96*se:+.3f}, {r.ev_pct+1.96*se:+.3f}]"
        print(f"{name:<24} {r.ev_pct:>+7.3f}%  {ci:>20}  "
              f"{r.win_rate:>7.2%}  {r.avg_wagered_per_shoe:>11,.0f}     {r.std_dev**2:>7.3f}")