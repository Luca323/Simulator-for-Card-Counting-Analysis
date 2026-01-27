from Card_Deck import Card, Deck, isSoft, calculate_hand_value


class Player:
    def __init__(self, bet_strategy=None):
        self.hand = []
        self.units = 200
        self.count = 0
        self.betting_strategy = bet_strategy

    def bet(self):
        if self.betting_strategy is None:
            raise ValueError("No betting strategy defined")

        bet = self.betting_strategy(self.count)

        if bet > self.units:
            raise ValueError(f"Insufficient units. Bet: {bet}, Available: {self.units}")

        self.units -= bet
        return bet

    def add_units(self, u: int):
        self.units += u

    def reset(self):
        self.hand = []

    def update_count(self, card: Card):
        pass

    def hit(self, c: Card):
        self.hand.append(c)

    def calculate_hand_value(self):
        return calculate_hand_value(self.hand)

    def is_soft(self):
        return isSoft(self.hand)

    def is_pair(self):
        """Check if hand is a pair (exactly 2 cards of same value)"""
        if len(self.hand) != 2:
            return False

        card1, card2 = self.hand[0], self.hand[1]

        # Normalize face cards to 10
        val1 = 10 if card1.value in ['J', 'Q', 'K'] else card1.value
        val2 = 10 if card2.value in ['J', 'Q', 'K'] else card2.value

        return val1 == val2

    def get_hand(self):
        return self.hand

    def is_busted(self):
        return self.calculate_hand_value() > 21

    def has_blackjack(self):
        """Check if player has blackjack (Ace + 10-value card)"""
        if len(self.hand) != 2:
            return False
        return self.calculate_hand_value() == 21


class Dealer(Player):
    def __init__(self, deck: Deck):
        super().__init__(bet_strategy=None)
        self.deck = deck
        self.deck.shuffle()

    def deal_card(self):
        """Deal a single card from the deck"""
        if self.is_empty():
            raise ValueError("Deck is empty or too low to deal")
        return self.deck.deal()

    def initial_deal(self):
        """Deal initial 2 cards to dealer"""
        self.hand = [self.deck.deal(), self.deck.deal()]

    def show_upcard(self):
        """Show the dealer's face-up card"""
        return self.hand[0] if self.hand else None


    def play(self):
        """Dealer hits on 16 or less, stands on 17 or more (including soft 17)"""
        while self.calculate_hand_value() < 17:
            self.hit(self.deck.deal())

    def get_deck(self):
        return self.deck

    def is_empty(self) -> bool:
        """Check if deck needs reshuffling (less than 7 cards for safety)"""
        return len(self.deck.cards) < 7

    def reset_deck(self):
        """Create and shuffle a new deck"""
        self.deck = Deck()
        self.deck.shuffle()

def tester():
    player = Player()
    dealer = Dealer(Deck())

    player.hit(Card("Hearts", "A"))
    player.hit(Card("Hearts", "A"))

    dealer.initial_deal()

    print(f"Dealer Upcard: {dealer.show_upcard()}")
    print(f"Dealer value: {dealer.calculate_hand_value()}, Player Value: {player.calculate_hand_value()}")



if __name__ == "__main__":
    tester()





















