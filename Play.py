from Card_Deck import Deck,Card, isSoft, calculate_hand_value
from Dealer_Player import Player, Dealer
from Strategies import basic, zero_memory
import numpy as np


def play_split_hands(hand1, hand2, dealer, strategy, original_bet, player):
    ''' Split logic -> return ((hand_values, bet_amounts), additional_wager)'''
    results = []
    bet_amounts = [original_bet, original_bet]  # Track each hand's bet separately
    additional_wager = 0  # Track additional money wagered (doubles)

    for i, hand in enumerate([hand1, hand2]):
        hand.hit(dealer.deal_card())

        first_card = hand.get_hand()[0]
        if first_card.value == 'A':
            results.append(hand.calculate_hand_value())
            continue

        action = strategy(
            dealer.show_upcard(),
            hand.calculate_hand_value(),
            False,
            hand.is_soft()
        )

        if action == 'double':
            player.units -= original_bet  # Deduct from player's bankroll
            bet_amounts[i] += original_bet  # Track the doubled bet
            additional_wager += original_bet  # Track additional wager
            hand.hit(dealer.deal_card())
        else:
            while action == 'hit' and not hand.is_busted():
                hand.hit(dealer.deal_card())
                action = strategy(
                    dealer.show_upcard(),
                    hand.calculate_hand_value(),
                    False,
                    hand.is_soft()
                )

        results.append(hand.calculate_hand_value())

    return (results, bet_amounts), additional_wager


def get_action(player, dealer, strategy):
    return strategy(
        dealer.show_upcard(),
        player.calculate_hand_value(),
        player.is_pair(),
        player.is_soft()
    )


def play_single_deck(deck: Deck, strategy=basic, verbose=False, starting_bankroll=200):
    """
    Play through a single deck with the given strategy.

    Args:
        deck: The deck to play with
        strategy: The strategy function to use
        verbose: If True, print detailed game information
        starting_bankroll: Starting amount for player

    Returns:
        tuple: (win_rate, final_profit_loss, games_played, total_wagered)
    """
    player = Player(zero_memory)
    player.units = starting_bankroll
    dealer = Dealer(deck)

    games_played = 0
    player_wins = 0
    player_losses = 0
    pushes = 0
    starting_units = player.units
    total_wagered = 0  # Track total amount wagered

    while not dealer.is_empty():
        # Bet logic
        try:
            bet_amount = player.bet()
            total_wagered += bet_amount  # Add initial bet
        except ValueError:
            # Player out of money
            if verbose:
                print(f"Player out of money after {games_played} games")
            break

        try:
            # Initial Deal
            player.hit(dealer.deal_card())
            player.hit(dealer.deal_card())
            dealer.initial_deal()

            games_played += 1

            if verbose:
                print(f"\n=== Game {games_played} ===")
                print(f"Cards remaining: {len(dealer.deck.cards)}")
                print(f"Player: {[str(c) for c in player.get_hand()]} = {player.calculate_hand_value()}")
                print(f"Dealer upcard: {dealer.show_upcard()}")

            # BlackJack Checks
            if dealer.has_blackjack():
                if player.has_blackjack():
                    player.add_units(bet_amount)  # Push
                    pushes += 1
                    if verbose:
                        print(f"Both BLACKJACK - Push")
                else:
                    player_losses += 1
                    if verbose:
                        print(f"Dealer BLACKJACK - Lost ${bet_amount}")

                player.reset()
                dealer.reset()
                continue

            if player.has_blackjack():
                winnings = bet_amount * 2.5
                player.add_units(winnings)
                player_wins += 1
                if verbose:
                    print(f"Player BLACKJACK! - Won ${winnings}")

                player.reset()
                dealer.reset()
                continue

            # Player Turn
            action = get_action(player, dealer, strategy)
            is_split = False

            if verbose:
                print(f"Action: {action}")

            # Handle initial action
            if action == 'split':
                is_split = True
                card1, card2 = player.hand[0], player.hand[1]

                hand1 = Player(player.betting_strategy)
                hand1.hit(card1)
                hand1.units = player.units

                hand2 = Player(player.betting_strategy)
                hand2.hit(card2)
                hand2.units = player.units

                player.units -= bet_amount
                total_wagered += bet_amount  # Add split bet

                # Updated to receive bet_amounts as well
                hand_values_and_bets, additional_wager = play_split_hands(hand1, hand2, dealer, strategy, bet_amount,
                                                                          player)
                total_wagered += additional_wager  # Add any doubles from split hands

            elif action == 'double':
                double_bet = player.bet()
                bet_amount += double_bet
                total_wagered += double_bet  # Add double bet
                player.hit(dealer.deal_card())
            else:
                while action == 'hit' and not player.is_busted():
                    player.hit(dealer.deal_card())
                    action = get_action(player, dealer, strategy)

            # Dealer's Turn
            if is_split:
                hand_values, bet_amounts = hand_values_and_bets
                should_dealer_play = any(val <= 21 for val in hand_values)
            else:
                should_dealer_play = not player.is_busted()

            if should_dealer_play:
                dealer.play()

            dealer_value = dealer.calculate_hand_value()
            dealer_busted = dealer.is_busted()

            # Resolution Logic
            winnings = 0

            if is_split:
                wins_this_split = 0
                losses_this_split = 0
                pushes_this_split = 0

                for i, (hand_value, hand_bet) in enumerate(zip(hand_values, bet_amounts), 1):
                    if hand_value > 21:
                        losses_this_split += 1
                        if verbose:
                            print(f"Hand {i}: Busted ({hand_value}) - Lost ${hand_bet}")
                    elif dealer_busted or hand_value > dealer_value:
                        winnings += hand_bet * 2  # Use actual bet for this hand
                        wins_this_split += 1
                        if verbose:
                            print(f"Hand {i}: Won ({hand_value} vs {dealer_value}) - Won ${hand_bet * 2}")
                    elif hand_value == dealer_value:
                        winnings += hand_bet  # Return actual bet
                        pushes_this_split += 1
                        if verbose:
                            print(f"Hand {i}: Push ({hand_value} vs {dealer_value}) - Returned ${hand_bet}")
                    else:
                        losses_this_split += 1
                        if verbose:
                            print(f"Hand {i}: Lost ({hand_value} vs {dealer_value}) - Lost ${hand_bet}")

                player.add_units(winnings)

                if wins_this_split > losses_this_split:
                    player_wins += 1
                elif losses_this_split > wins_this_split:
                    player_losses += 1
                else:
                    pushes += 1

            else:
                player_value = player.calculate_hand_value()

                if player.is_busted():
                    player_losses += 1
                    if verbose:
                        print(f"Player busted ({player_value}) - Lost ${bet_amount}")
                elif dealer_busted or player_value > dealer_value:
                    winnings = bet_amount * 2

                    player.add_units(winnings)
                    player_wins += 1
                    if verbose:
                        print(f"Won ({player_value} vs {dealer_value}) - Won ${winnings}")
                elif player_value == dealer_value:
                    winnings = bet_amount
                    player.add_units(winnings)
                    pushes += 1
                    if verbose:
                        print(f"Push ({player_value} vs {dealer_value}) - Returned ${bet_amount}")
                else:
                    player_losses += 1
                    if verbose:
                        print(f"Lost ({player_value} vs {dealer_value}) - Lost ${bet_amount}")

            if verbose:
                print(f'Dealer Hand: {[str(c) for c in dealer.get_hand()]} = {dealer.calculate_hand_value()}')
                print(f"Player units: ${player.units}")

            # Reset for next hand
            player.reset()
            dealer.reset()

        except IndexError as e:
            # Deck ran out of cards during dealing
            if verbose:
                print(f"Deck exhausted during game {games_played}: {e}")
            # Refund the bet that was placed but game didn't complete
            player.add_units(bet_amount)
            total_wagered -= bet_amount
            break
        except Exception as e:
            if verbose:
                print(f"Error during game {games_played}: {e}")
            # Refund the bet that was placed but game didn't complete
            player.add_units(bet_amount)
            total_wagered -= bet_amount
            break

    # Calculate statistics
    final_units = player.units
    profit_loss = final_units - starting_units
    win_rate = player_wins / games_played if games_played > 0 else 0

    if verbose:
        print(f"\n=== DECK COMPLETE ===")
        print(f"Games played: {games_played}")
        print(f"Wins: {player_wins}, Losses: {player_losses}, Pushes: {pushes}")
        print(f"Total wagered: ${total_wagered}")
        print(f"ROI: {(profit_loss / total_wagered * 100):.2f}%" if total_wagered > 0 else "N/A")

    return win_rate, profit_loss, games_played, total_wagered


# Example usage:
if __name__ == "__main__":
    deck2 = Deck()

    win_rate, profit_loss, games, total_wagered = play_single_deck(deck2, strategy=basic, verbose=True)

    print(f"Hand Win rate: {win_rate:.2%}")
    print(f"Profit/Loss: ${profit_loss}")
    print(f"Total wagered: ${total_wagered}")
    print(f"ROI: {(profit_loss / total_wagered * 100):.2f}%")



