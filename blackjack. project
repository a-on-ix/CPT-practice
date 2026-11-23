import random

while True:
    cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]

    player_hand = [random.choice(cards), random.choice(cards)]
    dealer_hand = [random.choice(cards), random.choice(cards)]

    print("Dealer: ? ", dealer_hand[1])
    print("You:", player_hand)

    player_total = sum(player_hand)
    aces = player_hand.count(11)

    while player_total > 21 and aces > 0:
        player_total = player_total - 10
        aces = aces - 1

    print("Your total:", player_total)

    while player_total < 21:
        choice = input("Hit or stand?: ").lower()

        if choice == "hit":
            new_card = random.choice(cards)
            player_hand.append(new_card)
            print("You drew:", new_card)
            print("You:", player_hand)

            player_total = sum(player_hand)
            aces = player_hand.count(11)

            while player_total > 21 and aces > 0:
                player_total = player_total - 10
                aces = aces - 1

            print("Your total:", player_total)

        elif choice == "stand":
            break

        else:
            print("Please enter hit or stand.")

    if player_total > 21:
        print("Dealer:", dealer_hand)
        print("You bust. Dealer wins.")
    else:
        dealer_total = sum(dealer_hand)
        aces = dealer_hand.count(11)

        while dealer_total > 21 and aces > 0:
            dealer_total = dealer_total - 10
            aces = aces - 1
        while dealer_total < 17:
            new_card = random.choice(cards)
            dealer_hand.append(new_card)
            dealer_total = sum(dealer_hand)
            aces = dealer_hand.count(11)

            while dealer_total > 21 and aces > 0:
                dealer_total = dealer_total - 10
                aces = aces - 1

        print("Dealer:", dealer_hand)
        print("Dealer total:", dealer_total)

        if dealer_total > 21:
            print("Dealer busts. You win!")
        elif player_total > dealer_total:
            print("You win!")
        elif player_total < dealer_total:
            print("Dealer wins.")
        else:
            print("It is a tie!")

    play_again = input("Play again? (yes/no): ").lower()
    if play_again != "yes":
        print("Thanks for playing!")
        break
