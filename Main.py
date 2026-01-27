from Play import play_single_deck,np
from Card_Deck import Deck
import matplotlib.pyplot as plt

def plot_histogram(profits):
    # Plot histogram
    plt.figure(figsize=(10, 6))
    plt.hist(profits, bins=30, color='skyblue', edgecolor='black')
    plt.axvline(np.mean(profits), color='red', linestyle='dashed', linewidth=2,
                label=f"Mean: {np.mean(profits):.2f}")
    plt.title("Distribution of Net Profit/Loss per Single-Deck Game")
    plt.xlabel("Net Profit/Loss (units)")
    plt.ylabel("Frequency")
    plt.legend()
    plt.show()

if __name__ == '__main__':
    scores = []
    for i in range(10000):
        scores.append(play_single_deck(Deck()))

    wr = sum(row[0] for row in scores) / len(scores)
    profit_dist = np.array([row[1] for row in scores])
    avg_win = sum(profit_dist) / len(scores)
    average_total_wager = sum(row[3] for row in scores) / len(scores)

    print(f"Average hand WR 10000: {wr * 100}%  Average P/L: {avg_win}, dist: {np.std(profit_dist)} AVG total wager: {average_total_wager}, House Edge: {-avg_win/average_total_wager}")


    # Assume 'scores' is your list of results from 1000 decks
    # scores[i][1] = final bankroll for deck i

    # Extract bankrolls
    final_bankrolls = [row[1] for row in scores]

    # Compute net profit/loss (subtract starting 200 units)
    profits = [b for b in final_bankrolls]
