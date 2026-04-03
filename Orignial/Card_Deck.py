from random import shuffle

class Card:
    def __init__(self, suit, value):
        self.suit = suit
        self.value = value

    def __str__(self):
        return f'{self.suit} {self.value}'

    def getValue(self):
        if self.value in ['J', 'Q', 'K']:
            return 10
        elif self.value == 'A':
            return 11
        else:
            return int(self.value)


class Deck:
    def __init__(self):
        self.cards = []
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        vals = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

        for suit in suits:
            for value in vals:
                self.cards.append(Card(suit, value))

        self.size = len(self.cards)

    def shuffle(self):
        shuffle(self.cards)

    def deal(self):
        self.size -= 1
        return self.cards.pop()

    def get_cards(self):
        return self.cards

    def __len__(self):
        return self.size

    def __str__(self):
        return f"Deck with {self.size} cards remaining"


class Shoe(Deck):
    def __init__(self, num_decks: int = 1):

        self.cards = []
        self.num_decks = num_decks
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        vals = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

        #Create multiple decks
        for _ in range(num_decks):
            for suit in suits:
                for value in vals:
                    self.cards.append(Card(suit, value))

        self.size = len(self.cards)


    def __str__(self):
        return f"Shoe with {self.num_decks} deck(s) - {self.size} cards remaining"


def calculate_hand_value(hand: list[Card]):
    """Calculate the best hand value (using Ace as 11 if possible)"""
    total = sum(c.getValue() for c in hand)
    ace_count = sum(1 for c in hand if c.value == 'A')

    # If we have aces counted as 11 and we're busting, convert to 1
    while total > 21 and ace_count > 0:
        total -= 10  # Change Ace from 11 to 1
        ace_count -= 1

    return total


def isSoft(hand: list[Card]):
    """Check if hand is soft (has an Ace counted as 11)"""
    if not any(c.value == 'A' for c in hand):
        return False

    hard_total = sum(1 if c.value == 'A' else c.getValue() for c in hand)
    soft_total = hard_total + 10  # Add 10 to count one Ace as 11 instead of 1

    return soft_total <= 21

def tester():
    CardDeck = Deck()
    CardDeck.shuffle()
    for c in CardDeck.get_cards():
        print(c)

    print(f'\n Dealt card: {CardDeck.deal()} \n')
    print(f'\n Dealt card: {CardDeck.deal()} \n')
    print(f'\n Dealt card: {CardDeck.deal()} \n')


    shoe = Shoe(num_decks=5)
    shoe.shuffle()
    print(shoe)
    print(f'\n Dealt shoe: {shoe.deal()} \n')

if __name__ == "__main__":
    tester()

