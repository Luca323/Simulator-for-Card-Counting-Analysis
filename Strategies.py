from Card_Deck import Deck, Card
from Dealer_Player import Player, Dealer

def zero_memory(s):
    return 10

def basic(dealer_upcard: Card, hand_value: int, is_pair: bool, soft: bool = False) -> str:
    """Basic blackjack strategy"""
    # Normalize dealer upcard
    if dealer_upcard.value in ['J', 'Q', 'K']:
        d_val = 10
    elif dealer_upcard.value == 'A':
        d_val = 11
    else:
        d_val = int(dealer_upcard.value)

    ACTION = {'H': 'hit', 'S': 'stand', 'D': 'double', 'P': 'split'}

    HARD = {
        4: {5: 'P', 6: 'P'},
        6: {2: 'P', 3: 'P', 4: 'P', 5: 'P', 6: 'P', 7: 'P'},
        8: {5: 'P', 6: 'P'},
        10: 'H',
        12: {2: 'P', 3: 'P', 4: 'P', 5: 'P', 6: 'P'},
        14: {2: 'P', 3: 'P', 4: 'P', 5: 'P', 6: 'P', 7: 'P'},
        16: 'P',
        18: {2: 'P', 3: 'P', 4: 'P', 5: 'P', 6: 'P', 8: 'P', 9: 'P'},
        20: 'S',
    }

    HARD_NO_PAIR = {
        4: 'H', 5: 'H', 6: 'H', 7: 'H', 8: 'H',
        9: {3: 'D', 4: 'D', 5: 'D', 6: 'D'},
        10: {2: 'D', 3: 'D', 4: 'D', 5: 'D', 6: 'D', 7: 'D', 8: 'D', 9: 'D'},
        11: {2: 'D', 3: 'D', 4: 'D', 5: 'D', 6: 'D', 7: 'D', 8: 'D', 9: 'D', 10: 'D', 11: 'D'},
        12: {4: 'S', 5: 'S', 6: 'S'},
        13: {2: 'S', 3: 'S', 4: 'S', 5: 'S', 6: 'S'},
        14: {2: 'S', 3: 'S', 4: 'S', 5: 'S', 6: 'S'},
        15: {2: 'S', 3: 'S', 4: 'S', 5: 'S', 6: 'S'},
        16: {2: 'S', 3: 'S', 4: 'S', 5: 'S', 6: 'S'},
        17: 'S', 18: 'S', 19: 'S', 20: 'S', 21: 'S'
    }

    SOFT = {
        12: 'P',  # Pair of Aces
        13: {5: 'D', 6: 'D'},  # A,2
        14: {5: 'D', 6: 'D'},  # A,3
        15: {4: 'D', 5: 'D', 6: 'D'},  # A,4
        16: {4: 'D', 5: 'D', 6: 'D'},  # A,5
        17: {3: 'D', 4: 'D', 5: 'D', 6: 'D'},  # A,6
        18: {2: 'S', 3: 'D', 4: 'D', 5: 'D', 6: 'D', 7: 'S', 8: 'S'},  # A,7 - stand vs 2,7,8; double vs 3-6; hit vs 9,10,A
        19: 'S',  # A,8
        20: 'S',  # A,9
        21: 'S'   # A,10
    }

    if soft:
        table = SOFT
    elif is_pair:
        table = HARD
    else:
        table = HARD_NO_PAIR

    row = table.get(hand_value, 'H')

    if isinstance(row, dict):
        return ACTION[row.get(d_val, 'H')]
    else:
        return ACTION[row]



def tester():
    # Simple betting strategy
    def flat_bet(count):
        return 10

    player = Player(bet_strategy=flat_bet)
    dealer = Dealer(Deck())

    # Deal cards
    player.hit(Card("Hearts", "8"))
    player.hit(Card("Spades", "8"))
    dealer.initial_deal()

    print(f"Player hand: {[str(c) for c in player.get_hand()]}")
    print(f"Player value: {player.calculate_hand_value()}")
    print(f"Player soft: {player.is_soft()}")
    print(f"Player pair: {player.is_pair()}")
    print()
    print(f"Dealer upcard: {dealer.show_upcard()}")
    print(f"Dealer value: {dealer.calculate_hand_value()}")
    print()

    # Get strategy recommendation
    action = basic(
        dealer.show_upcard(),
        player.calculate_hand_value(),
        player.is_pair(),
        player.is_soft()
    )
    print(f"Recommended action: {action}")



if __name__ == '__main__':
    tester()

