"""
engine.py
---------
The simulation engine.

Architecture
------------
EventBus
    Maintains a list of subscriber callables.  Any component (ledger,
    logger, counter display …) can subscribe to receive every event.
    The bus is the ONLY way events flow — no component calls another directly.

HandState
    A plain dataclass holding the mutable cards/bets for one hand slot
    during a single round.  Discarded after ROUND_ENDED.

Engine
    Orchestrates one shoe.  For each round it:
      1. Fires ROUND_STARTED
      2. Places bets  (fires BET_PLACED)
      3. Deals initial cards  (fires CARD_DEALT × 4)
      4. Checks for blackjacks
      5. Runs the player state machine (hit/stand/double/split)
      6. Reveals hole card and runs the dealer  (fires HOLE_CARD_REVEALED)
      7. Settles all hands  (fires HAND_SETTLED per hand)
      8. Fires ROUND_ENDED
    When the shoe passes the cut card it fires SHOE_EXHAUSTED and stops.

The engine contains zero financial logic.  Money tracking is entirely
delegated to the Ledger via events.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from events import (
    Card, EventType, Outcome,
    ShoeShuffledEvent, RoundStartedEvent, BetPlacedEvent, CardDealtEvent,
    HoleCardRevealedEvent, PlayerActionEvent, DoubleDownEvent,
    SplitInitiatedEvent, PlayerBlackjackEvent, DealerBlackjackEvent,
    BlackjackPushEvent, HandSettledEvent, RoundEndedEvent, ShoeExhaustedEvent,
)
from shoe import Shoe
from hand import hand_value, is_soft, is_pair, is_blackjack, is_busted
from count import CounterState


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

class EventBus:
    def __init__(self):
        self._subscribers: List[Callable] = []

    def subscribe(self, fn: Callable) -> None:
        self._subscribers.append(fn)

    def fire(self, event) -> None:
        for sub in self._subscribers:
            sub(event)


# ---------------------------------------------------------------------------
# Hand state  (one per active hand slot within a round)
# ---------------------------------------------------------------------------

@dataclass
class HandState:
    hand_id:  int
    cards:    List[Card] = field(default_factory=list)
    bet:      float = 0.0
    done:     bool  = False   # True once stand/bust/double/split-ace

    @property
    def value(self)  -> int:   return hand_value(self.cards)
    @property
    def soft(self)   -> bool:  return is_soft(self.cards)
    @property
    def pair(self)   -> bool:  return is_pair(self.cards)
    @property
    def busted(self) -> bool:  return is_busted(self.cards)
    @property
    def blackjack(self) -> bool: return is_blackjack(self.cards)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine:
    """
    Drives one shoe from shuffle to cut-card.

    Parameters
    ----------
    shoe            : Shoe instance (will be shuffled fresh on run())
    playing_strategy: fn(upcard, hand_value, pair, soft) → action str
    betting_strategy: fn(true_count) → bet amount float
    counter         : CounterState  (owns running/true count)
    bus             : EventBus  (all events published here)
    bankroll        : starting bankroll — tracked by ledger, but engine
                      needs it to know when the player is bust
    penetration     : fraction of shoe to deal before reshuffling (0–1)
    """

    def __init__(
        self,
        shoe:             Shoe,
        playing_strategy: Callable,
        betting_strategy: Callable,
        counter:          CounterState,
        bus:              EventBus,
        starting_bankroll: float = 1000.0,
        penetration:      float  = 0.75,
    ):
        self._shoe      = shoe
        self._play_fn   = playing_strategy
        self._bet_fn    = betting_strategy
        self._counter   = counter
        self._bus       = bus
        self._bankroll  = starting_bankroll   # kept in sync via events
        self._pen       = penetration
        self._round     = 0

        # Subscribe engine's own bankroll mirror to events so it
        # can abort when the player has insufficient funds.
        self._bus.subscribe(self._mirror_bankroll)

    # ------------------------------------------------------------------
    # Bankroll mirror  (engine shadow-tracks balance for bust detection)
    # ------------------------------------------------------------------

    def _mirror_bankroll(self, event) -> None:
        t = event.type
        if t == EventType.BET_PLACED:
            self._bankroll -= event.amount
        elif t == EventType.DOUBLE_DOWN:
            self._bankroll -= event.extra_bet
        elif t == EventType.HAND_SETTLED:
            if event.outcome == Outcome.WIN:
                self._bankroll += event.bet * 2
            elif event.outcome == Outcome.PUSH:
                self._bankroll += event.bet
        elif t == EventType.PLAYER_BLACKJACK:
            self._bankroll += event.payout
        elif t == EventType.BLACKJACK_PUSH:
            self._bankroll += event.bet

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Play the shoe to cut-card (or bankroll exhaustion)."""
        self._shoe.shuffle()
        self._counter.reset()
        self._bus.fire(ShoeShuffledEvent(
            num_decks   = self._shoe.num_decks,
            total_cards = len(self._shoe),
        ))

        while not self._shoe.past_cut_card(self._pen):
            # Guard: need at least 4 cards to deal a round (2 player + 2 dealer).
            # Without this a round can start then crash mid-deal on a thin shoe.
            if self._shoe.cards_remaining < 4:
                break

            # Update true count before each betting decision
            self._counter.update_true_count(self._shoe.decks_remaining)
            bet = self._bet_fn(self._counter.true_count)

            if bet > self._bankroll:
                break   # bankrupt

            self._round += 1
            try:
                self._play_round(bet)
            except RuntimeError:
                # Shoe ran dry mid-round (can happen on single deck with splits/doubles).
                # Refund the bet as a push and stop — the round never completed.
                self._bus.fire(BlackjackPushEvent(bet=bet))
                self._bus.fire(RoundEndedEvent(
                    round_number             = self._round,
                    net_this_round           = 0.0,
                    total_wagered_this_round = bet,
                    bankroll                 = self._bankroll,
                ))
                break

        self._bus.fire(ShoeExhaustedEvent(
            rounds_played = self._round,
            cards_dealt   = self._shoe.cards_dealt,
        ))

    # ------------------------------------------------------------------
    # Round orchestration
    # ------------------------------------------------------------------

    def _play_round(self, bet: float) -> None:
        self._bus.fire(RoundStartedEvent(
            round_number   = self._round,
            cards_remaining= self._shoe.cards_remaining,
            running_count  = self._counter.running_count,
            true_count     = self._counter.true_count,
            bankroll       = self._bankroll,
        ))

        # ---- Bets ----
        self._bus.fire(BetPlacedEvent(
            hand_id        = 0,
            amount         = bet,
            bankroll_after = self._bankroll - bet,
            reason         = 'initial',
        ))

        # ---- Initial deal ----
        p1 = self._deal_to('player', hand_id=0, face_up=True)
        p2 = self._deal_to('player', hand_id=0, face_up=True)
        d1 = self._deal_to('dealer', hand_id=-1, face_up=True)
        d2 = self._deal_to('dealer', hand_id=-1, face_up=False)  # hole card — NOT counted yet

        player_hand  = HandState(hand_id=0, cards=[p1, p2], bet=bet)
        dealer_cards = [d1, d2]

        round_net   = 0.0
        total_wager = bet

        # ---- Blackjack checks ----
        dealer_bj = is_blackjack(dealer_cards)
        player_bj = player_hand.blackjack

        if dealer_bj:
            # Reveal hole card when dealer checks for blackjack
            delta = self._counter.observe(d2)
            self._bus.fire(HoleCardRevealedEvent(card=d2, count_update=delta))
            self._bus.fire(DealerBlackjackEvent(dealer_hand=list(dealer_cards), bet=bet))

            if player_bj:
                self._bus.fire(BlackjackPushEvent(bet=bet))
                round_net = 0.0
            else:
                # Player loses — bet already deducted via BET_PLACED; nothing returned
                round_net = -bet

            self._fire_round_ended(round_net, total_wager)
            return

        if player_bj:
            delta = self._counter.observe(d2)
            self._bus.fire(HoleCardRevealedEvent(card=d2, count_update=delta))
            payout = bet * 2.5
            self._bus.fire(PlayerBlackjackEvent(payout=payout, bet=bet))
            round_net = bet * 1.5
            self._fire_round_ended(round_net, total_wager)
            return

        # ---- Player turn ----
        # Build the list of hands to play (may grow if split occurs)
        hands: List[HandState] = [player_hand]
        next_hand_id = 1

        hand_idx = 0
        while hand_idx < len(hands):
            h = hands[hand_idx]

            # If this is a split-ace, one card already dealt — just mark done
            if h.done:
                hand_idx += 1
                continue

            while not h.done:
                action = self._play_fn(d1, h.value, h.pair, h.soft)
                self._bus.fire(PlayerActionEvent(
                    hand_id     = h.hand_id,
                    action      = action,
                    hand_value  = h.value,
                    dealer_upcard = d1,
                ))

                if action == 'stand':
                    h.done = True

                elif action == 'hit':
                    card = self._deal_to(f'player', hand_id=h.hand_id, face_up=True)
                    h.cards.append(card)
                    if h.busted:
                        h.done = True

                elif action == 'double':
                    extra = h.bet   # double always matches original bet
                    self._bus.fire(DoubleDownEvent(
                        hand_id   = h.hand_id,
                        extra_bet = extra,
                        card      = Card('?', '?'),   # placeholder; real card below
                        count_update = 0.0,
                    ))
                    card = self._deal_to(f'player', hand_id=h.hand_id, face_up=True)
                    h.cards.append(card)
                    h.bet   += extra
                    total_wager += extra
                    # Patch the event with the real card (fire a CARD_DEALT instead)
                    # The DOUBLE_DOWN already fired the financial side; card is tracked
                    # via the CARD_DEALT fired inside _deal_to above.
                    h.done = True

                elif action == 'split':
                    extra_bet = h.bet
                    self._bus.fire(BetPlacedEvent(
                        hand_id        = next_hand_id,
                        amount         = extra_bet,
                        bankroll_after = self._bankroll - extra_bet,
                        reason         = 'split',
                    ))
                    total_wager += extra_bet

                    card_a, card_b = h.cards[0], h.cards[1]
                    new_id = next_hand_id
                    next_hand_id += 1

                    self._bus.fire(SplitInitiatedEvent(
                        original_hand_id = h.hand_id,
                        new_hand_ids     = [h.hand_id, new_id],
                        extra_bet        = extra_bet,
                    ))

                    # Deal one card to each split hand
                    new_card_a = self._deal_to('player', hand_id=h.hand_id, face_up=True)
                    new_card_b = self._deal_to('player', hand_id=new_id,    face_up=True)

                    # Rebuild original hand with first split card + new card
                    h.cards = [card_a, new_card_a]

                    # Create second hand
                    hand_b = HandState(hand_id=new_id, cards=[card_b, new_card_b], bet=extra_bet)

                    # If split aces, only one card each — mark both done
                    if card_a.value == 'A':
                        h.done      = True
                        hand_b.done = True

                    hands.append(hand_b)
                    # Don't break — continue playing current hand (h)

            hand_idx += 1

        # ---- Dealer turn ----
        all_busted = all(h.busted for h in hands)

        if not all_busted:
            # Reveal hole card
            delta = self._counter.observe(d2)
            self._bus.fire(HoleCardRevealedEvent(card=d2, count_update=delta))

            # Dealer hits until 17+ (S17 rule)
            while hand_value(dealer_cards) < 17:
                card = self._shoe.deal()
                delta = self._counter.observe(card)
                self._bus.fire(CardDealtEvent(
                    card         = card,
                    recipient    = 'dealer',
                    hand_id      = -1,
                    face_up      = True,
                    count_update = delta,
                ))
                dealer_cards.append(card)

        dealer_val    = hand_value(dealer_cards)
        dealer_busted = is_busted(dealer_cards)

        # ---- Settlement ----
        for h in hands:
            if h.busted:
                outcome = Outcome.LOSS
                net     = -h.bet
            elif dealer_busted or h.value > dealer_val:
                outcome = Outcome.WIN
                net     = h.bet
            elif h.value == dealer_val:
                outcome = Outcome.PUSH
                net     = 0.0
            else:
                outcome = Outcome.LOSS
                net     = -h.bet

            self._bus.fire(HandSettledEvent(
                hand_id      = h.hand_id,
                outcome      = outcome,
                bet          = h.bet,
                net          = net,
                player_total = h.value,
                dealer_total = dealer_val,
            ))
            round_net += net

        self._fire_round_ended(round_net, total_wager)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _deal_to(self, recipient: str, hand_id: int, face_up: bool) -> Card:
        """Deal one card, update count if face-up, fire CARD_DEALT."""
        card = self._shoe.deal()
        if face_up:
            delta = self._counter.observe(card)
        else:
            delta = 0.0   # hole card — counted only when revealed
        self._bus.fire(CardDealtEvent(
            card         = card,
            recipient    = recipient,
            hand_id      = hand_id,
            face_up      = face_up,
            count_update = delta,
        ))
        return card

    def _fire_round_ended(self, net: float, wagered: float) -> None:
        self._bus.fire(RoundEndedEvent(
            round_number          = self._round,
            net_this_round        = net,
            total_wagered_this_round = wagered,
            bankroll              = self._bankroll,
        ))