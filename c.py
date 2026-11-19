import random
import select
import sys
import termios
import time
import tty
from dataclasses import dataclass, field


SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
BLACKJACK = 21


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        if self.rank == "A":
            return 11
        if self.rank in ("K", "Q", "J"):
            return 10
        return int(self.rank)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    bet: float = 10
    from_split: bool = False
    stood: bool = False
    surrendered: bool = False
    doubled: bool = False

    def total_and_soft(self) -> tuple[int, bool]:
        total = sum(card.value for card in self.cards)
        aces = sum(card.rank == "A" for card in self.cards)
        while total > BLACKJACK and aces:
            total -= 10
            aces -= 1
        return total, aces > 0

    @property
    def total(self) -> int:
        return self.total_and_soft()[0]

    @property
    def is_blackjack(self) -> bool:
        return not self.from_split and len(self.cards) == 2 and self.total == BLACKJACK

    @property
    def is_busted(self) -> bool:
        return self.total > BLACKJACK

    def can_split(self) -> bool:
        return (
            len(self.cards) == 2
            and card_value(self.cards[0]) == card_value(self.cards[1])
        )

    def __str__(self) -> str:
        if not self.cards:
            return "(empty)"
        total, soft = self.total_and_soft()
        label = "soft " if soft and total <= BLACKJACK else ""
        return f"{' '.join(map(str, self.cards))} [{label}{total}]"


def card_value(card: Card) -> int:
    return 10 if card.rank in ("10", "J", "Q", "K") else card.value


class Shoe:
    def __init__(self, decks: int = 6) -> None:
        self.decks = decks
        self.cards: list[Card] = []
        self.shuffle()

    def shuffle(self) -> None:
        self.cards = [
            Card(rank, suit)
            for _ in range(self.decks)
            for suit in SUITS
            for rank in RANKS
        ]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if len(self.cards) < 52:
            print("\n[The shoe was cut. Shuffling a new set of decks.]")
            self.shuffle()
        return self.cards.pop()


class BlackjackGame:
    def __init__(self) -> None:
        self.shoe = Shoe()
        self.bankroll = 1000000.0
        self.current_bet = 10.0
        self.round_number = 0
        self.stats = {
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "blackjacks": 0,
            "busts": 0,
        }

    def money(self, amount: float) -> str:
        return f"${amount:,.2f}"

    def ask_choice(self, prompt: str, choices: tuple[str, ...]) -> str:
        while True:
            answer = input(prompt).strip().lower()
            if answer in choices:
                return answer
            print(f"Please enter one of: {', '.join(choices)}")

    def choose_bet(self) -> float:
        print(f"\nBankroll: {self.money(self.bankroll)}")
        while True:
            try:
                raw = input(
                    f"Bet (default {self.money(self.current_bet)}, 'all', or 'q'): "
                ).strip()
                if raw.lower() in ("", "d"):
                    bet = self.current_bet
                elif raw.lower() == "q":
                    return 0
                elif raw.lower() in ("all", "all-in", "allin"):
                    bet = self.bankroll
                else:
                    bet = float(raw)
                if bet < 5:
                    print("Minimum bet is $5.")
                elif bet > self.bankroll:
                    print("You do not have enough bankroll.")
                else:
                    self.current_bet = bet
                    return bet
            except ValueError:
                print("Enter a valid dollar amount.")

    def deal_round(self, bet: float) -> tuple[list[Hand], Hand]:
        player = Hand(bet=bet)
        dealer = Hand()
        self.bankroll -= bet
        for hand in (player, dealer, player, dealer):
            hand.cards.append(self.shoe.draw())
        return [player], dealer

    def dealer_upcard(self, dealer: Hand) -> str:
        return str(dealer.cards[0])

    def offer_insurance(self, dealer: Hand, base_bet: float) -> float:
        if dealer.cards[0].rank != "A":
            return 0
        if self.bankroll < base_bet / 2:
            print("Insurance unavailable: insufficient bankroll.")
            return 0
        choice = self.ask_choice(
            f"Insurance costs {self.money(base_bet / 2)} (y/n)? ",
            ("y", "n", "yes", "no"),
        )
        if choice not in ("y", "yes"):
            return 0
        cost = base_bet / 2
        self.bankroll -= cost
        if dealer.is_blackjack:
            payout = cost * 3
            self.bankroll += payout
            print(f"Insurance wins {self.money(payout - cost)}!")
            return cost
        print("Insurance loses.")
        return cost

    def play_hand(self, hand: Hand, hands: list[Hand], dealer: Hand) -> None:
        if hand.is_busted or hand.surrendered:
            return

        if len(hand.cards) == 2 and hand.cards[0].rank == "A" and hand.cards[1].rank == "A":
            hand.cards.append(self.shoe.draw())
            print(f"  Split aces receive one card: {hand}")
            return

        while not hand.stood and not hand.is_busted:
            actions = ["h", "s"]
            if len(hand.cards) == 2:
                actions.append("d")
                actions.append("u")
                if hand.can_split() and len(hands) < 4 and self.bankroll >= hand.bet:
                    actions.append("p")

            print(f"\nHand: {hand}")
            action = self.ask_choice(
                "Action ([h]it, [s]tand, [d]ouble, [p]split, s[u]rrender): ",
                tuple(actions),
            )

            if action in ("h",):
                hand.cards.append(self.shoe.draw())
                print(f"  Drew {hand.cards[-1]}: {hand}")
            elif action in ("s",):
                hand.stood = True
            elif action in ("d",):
                if self.bankroll < hand.bet:
                    print("  Not enough bankroll to double.")
                    continue
                self.bankroll -= hand.bet
                hand.bet *= 2
                hand.doubled = True
                hand.cards.append(self.shoe.draw())
                print(f"  Doubled. Drew {hand.cards[-1]}: {hand}")
                hand.stood = True
            elif action in ("p",):
                self.split_hand(hand, hands)
                return
            elif action in ("u",):
                hand.surrendered = True
                print("  Hand surrendered.")

    def split_hand(self, hand: Hand, hands: list[Hand]) -> None:
        self.bankroll -= hand.bet
        first = Hand(
            cards=[hand.cards[0], self.shoe.draw()],
            bet=hand.bet,
            from_split=True,
        )
        second = Hand(
            cards=[hand.cards[1], self.shoe.draw()],
            bet=hand.bet,
            from_split=True,
        )
        index = hands.index(hand)
        hands[index:index + 1] = [first, second]
        print(f"\nSplit into:\n  1: {first}\n  2: {second}")

        for new_hand in (first, second):
            if new_hand.cards[0].rank == "A":
                new_hand.cards.append(self.shoe.draw())
                print(f"  Split ace hand gets one card: {new_hand}")
            else:
                self.play_hand(new_hand, hands, Hand())

    def play_dealer(self, dealer: Hand) -> None:
        print("\nDealer reveals:")
        print(f"  {dealer}")
        while dealer.total < 17:
            dealer.cards.append(self.shoe.draw())
            print(f"  Dealer draws {dealer.cards[-1]}: {dealer}")

    def settle_hand(self, hand: Hand, dealer: Hand) -> str:
        if hand.surrendered:
            refund = hand.bet / 2
            self.bankroll += refund
            self.stats["losses"] += 1
            return f"Surrendered — lost {self.money(hand.bet - refund)}"

        if hand.is_busted:
            self.stats["busts"] += 1
            self.stats["losses"] += 1
            return f"Bust — lost {self.money(hand.bet)}"

        if dealer.is_busted:
            payout = hand.bet * 2
            self.bankroll += payout
            self.stats["wins"] += 1
            return f"Dealer busts — won {self.money(hand.bet)}"

        if hand.is_blackjack and dealer.is_blackjack:
            self.bankroll += hand.bet
            self.stats["pushes"] += 1
            return "Both have blackjack — push"

        if hand.is_blackjack:
            payout = hand.bet * 2.5
            self.bankroll += payout
            self.stats["blackjacks"] += 1
            self.stats["wins"] += 1
            return f"Blackjack — won {self.money(payout - hand.bet)}"

        if dealer.is_blackjack:
            self.stats["losses"] += 1
            return "Dealer has blackjack — lost"

        if hand.total > dealer.total:
            payout = hand.bet * 2
            self.bankroll += payout
            self.stats["wins"] += 1
            return f"Won {self.money(hand.bet)}"
        if hand.total < dealer.total:
            self.stats["losses"] += 1
            return f"Lost {self.money(hand.bet)}"

        self.bankroll += hand.bet
        self.stats["pushes"] += 1
        return f"Push — {self.money(hand.bet)} returned"

    def play_round(self) -> bool:
        bet = self.choose_bet()
        if bet == 0:
            return False

        self.round_number += 1
        hands, dealer = self.deal_round(bet)
        player = hands[0]

        print(f"\n===== ROUND {self.round_number} =====")
        print(f"Dealer shows: {self.dealer_upcard(dealer)}")
        print(f"Your hand: {player}")

        insurance_cost = self.offer_insurance(dealer, bet)
        del insurance_cost  # The insurance payout is handled when it is offered.

        if dealer.is_blackjack:
            print(f"\nDealer has blackjack: {dealer}")
            for index, hand in enumerate(hands, 1):
                print(f"  Hand {index}: {self.settle_hand(hand, dealer)}")
            self.show_result()
            return self.bankroll >= 5

        if player.is_blackjack:
            print(f"\nNatural blackjack: {player}")
            print(f"  {self.settle_hand(player, dealer)}")
            self.show_result()
            return self.bankroll >= 5

        for hand in hands.copy():
            self.play_hand(hand, hands, dealer)

        needs_dealer = any(
            not hand.is_busted and not hand.surrendered for hand in hands
        )
        if needs_dealer:
            self.play_dealer(dealer)

        print("\nRound result:")
        for index, hand in enumerate(hands, 1):
            result = self.settle_hand(hand, dealer)
            print(f"  Hand {index}: {hand} — {result}")
        self.show_result()
        return self.bankroll >= 5

    def show_result(self) -> None:
        print(f"Bankroll: {self.money(self.bankroll)}")

    def show_statistics(self) -> None:
        total = sum(
            self.stats[key] for key in ("wins", "losses", "pushes")
        )
        win_rate = (self.stats["wins"] / total * 100) if total else 0
        print("\n===== Session Statistics =====")
        print(f"Rounds: {self.round_number}")
        print(f"Wins: {self.stats['wins']}")
        print(f"Losses: {self.stats['losses']}")
        print(f"Pushes: {self.stats['pushes']}")
        print(f"Blackjacks: {self.stats['blackjacks']}")
        print(f"Busts: {self.stats['busts']}")
        print(f"Win rate: {win_rate:.1f}%")
        print(f"Final bankroll: {self.money(self.bankroll)}")

    def run(self) -> float:
        print("\n" + "=" * 48)
        print("          BLACK JACK — 6-DECK CASINO")
        print("=" * 48)
        print("Dealer stands on 17. Blackjack pays 3:2.")
        print("Actions: h=hit s=stand d=double p=split u=surrender")
        print("Betting: enter 'all' to bet the entire bankroll.")

        try:
            while self.bankroll >= 5:
                if not self.play_round():
                    break
                again = self.ask_choice(
                    "\nPlay another round or return to lobby? (y/lobby): ",
                    ("y", "yes", "lobby", "l"),
                )
                if again in ("lobby", "l"):
                    break
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession ended.")

        if self.bankroll < 5:
            print("\nYou are below the table minimum.")
        self.show_statistics()
        return self.bankroll


class RouletteGame:
    REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

    def __init__(self, bankroll: float) -> None:
        self.bankroll = bankroll
        self.current_bet = 10.0
        self.spins = 0
        self.wins = 0

    def money(self, amount: float) -> str:
        return f"${amount:,.2f}"

    def ask_choice(self, prompt: str, choices: tuple[str, ...]) -> str:
        while True:
            answer = input(prompt).strip().lower()
            if answer in choices:
                return answer
            print(f"Please enter one of: {', '.join(choices)}")

    def choose_bet_amount(self) -> float:
        while True:
            try:
                raw = input(
                    f"Bet amount (default {self.money(self.current_bet)}, 'all', or 'q'): "
                ).strip()
                if raw.lower() in ("", "d"):
                    amount = self.current_bet
                elif raw.lower() in ("all", "all-in", "allin"):
                    amount = self.bankroll
                elif raw.lower() in ("q", "quit", "lobby"):
                    return 0
                else:
                    amount = float(raw)
                if amount < 5:
                    print("Minimum bet is $5.")
                elif amount > self.bankroll:
                    print("You do not have enough bankroll.")
                else:
                    self.current_bet = amount
                    return amount
            except ValueError:
                print("Enter a valid dollar amount.")

    def choose_wager(self) -> tuple[str, str, float] | None:
        print("\nWager types:")
        print("  1-36  — straight number")
        print("  red/black, odd/even")
        print("  low (1-18), high (19-36)")
        print("  dozen1/2/3")
        print("  column1/2/3")
        wager = input("Place your wager: ").strip().lower()

        if wager.isdigit():
            number = int(wager)
            if not 0 <= number <= 36:
                print("Choose a number from 0 to 36.")
                return None
            return "straight", str(number), 35

        payouts = {
            "red": 1,
            "black": 1,
            "odd": 1,
            "even": 1,
            "low": 1,
            "high": 1,
            "dozen1": 2,
            "dozen2": 2,
            "dozen3": 2,
            "column1": 2,
            "column2": 2,
            "column3": 2,
        }
        if wager in payouts:
            return wager, wager, payouts[wager]
        print("Invalid wager.")
        return None

    def wins_wager(self, wager: str, target: str, number: int) -> bool:
        if wager == "straight":
            return number == int(target)
        if number == 0:
            return False
        if wager == "red":
            return number in self.REDS
        if wager == "black":
            return number not in self.REDS
        if wager == "odd":
            return number % 2 == 1
        if wager == "even":
            return number % 2 == 0
        if wager == "low":
            return 1 <= number <= 18
        if wager == "high":
            return 19 <= number <= 36
        if wager.startswith("dozen"):
            dozen = int(wager[-1])
            return (dozen - 1) * 12 < number <= dozen * 12
        if wager.startswith("column"):
            column = int(wager[-1])
            return number > 0 and (number - column) % 3 == 0
        return False

    def spin(self) -> int:
        wheel = list(range(37))
        return random.choice(wheel)

    def show_wheel_result(self, number: int) -> None:
        if number == 0:
            color = "green"
        elif number in self.REDS:
            color = "red"
        else:
            color = "black"
        print(f"\nThe wheel stops on {number} {color.upper()}!")

    def run(self) -> float:
        print("\n" + "=" * 48)
        print("           EUROPEAN ROULETTE")
        print("=" * 48)
        print("Single zero • Outside bets pay 1:1 • Dozens/columns pay 2:1")

        try:
            while self.bankroll >= 5:
                print(f"\nBankroll: {self.money(self.bankroll)}")
                wager = self.choose_wager()
                if wager is None:
                    continue

                amount = self.choose_bet_amount()
                if amount == 0:
                    break

                wager_type, target, payout = wager
                self.bankroll -= amount
                number = self.spin()
                self.spins += 1
                self.show_wheel_result(number)

                if self.wins_wager(wager_type, target, number):
                    profit = amount * payout
                    self.bankroll += amount + profit
                    self.wins += 1
                    print(f"You win {self.money(profit)}!")
                else:
                    print(f"You lose {self.money(amount)}.")
                print(f"Bankroll: {self.money(self.bankroll)}")

                again = self.ask_choice(
                    "\nSpin again or return to lobby? (y/lobby): ",
                    ("y", "yes", "lobby", "l"),
                )
                if again in ("lobby", "l"):
                    break
        except (KeyboardInterrupt, EOFError):
            print("\n\nSession ended.")

        print("\n===== Roulette Statistics =====")
        print(f"Spins: {self.spins}")
        print(f"Wins: {self.wins}")
        print(f"Final bankroll: {self.money(self.bankroll)}")
        return self.bankroll


class GeometryDash:
    def __init__(self) -> None:
        self.attempt = 1
        self.best_attempt = 0
        self.best_progress = 0.0

    def read_key(self, timeout: float) -> str:
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if readable:
            return sys.stdin.read(1)
        return ""

    def run_wave(self) -> None:
        print("\n" + "=" * 48)
        print("                 GEOMETRY DASH — WAVE")
        print("=" * 48)
        print("Hold SPACE to rise. Release SPACE to fall.")
        print("Avoid the walls and reach 100%.")
        print("Press Q to return to the Geometry Dash menu.")
        input("Press Enter to begin...")

        try:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            in_raw_terminal = True
        except termios.error:
            old_settings = None
            in_raw_terminal = False

        obstacles = {
            12: (0, 5),
            13: (0, 5),
            24: (6, 11),
            25: (6, 11),
            36: (0, 4),
            37: (0, 4),
            48: (7, 11),
            49: (7, 11),
            60: (0, 6),
            61: (0, 6),
            72: (5, 11),
            73: (5, 11),
            84: (0, 5),
            85: (0, 5),
        }

        try:
            while True:
                wave_y = 5.5
                distance = 0
                won = False
                crashed = False

                print(f"\nWave attempt {self.attempt} | Hold SPACE")

                for distance in range(101):
                    key = "" if not in_raw_terminal else self.read_key(0.055)
                    if key.lower() == "q":
                        print("\nReturned to the lobby.")
                        return

                    if key == " ":
                        wave_y += 0.9
                    else:
                        wave_y -= 0.55

                    if wave_y < 0.5:
                        wave_y = 0.5
                        crashed = True
                    elif wave_y > 10.5:
                        wave_y = 10.5
                        crashed = True

                    sys.stdout.write("\033[H\033[2J")
                    sys.stdout.write(
                        f"WAVE  ATTEMPT {self.attempt}  |  PROGRESS {distance}%\n"
                    )
                    sys.stdout.write("=" * 40 + "\n")
                    wave_row = int(round(wave_y))

                    for row in range(11, -1, -1):
                        line = list(" " * 40)
                        if row == wave_row:
                            line[8] = "◆"

                        view_start = distance - 8
                        for x in range(40):
                            world_x = view_start + x
                            wall = obstacles.get(world_x)
                            if wall and wall[0] <= row <= wall[1]:
                                line[x] = "█"
                        sys.stdout.write("".join(line) + "\n")
                    sys.stdout.flush()

                    wall = obstacles.get(distance)
                    if wall and wall[0] <= wave_row <= wall[1]:
                        crashed = True

                    if crashed:
                        break
                    if distance >= 100:
                        won = True
                        break
                    time.sleep(0.055)

                progress = float(distance)
                if progress > self.best_progress:
                    self.best_progress = progress

                if won:
                    print("\nWAVE LEVEL COMPLETE!")
                    print("You reached 100%.")
                    break

                print(f"\nWAVE CRASHED at {distance}%.")
                retry = input("Retry or lobby? (r/l): ").strip().lower()
                if retry in ("l", "lobby", "q"):
                    break
                self.attempt += 1
        finally:
            if old_settings is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()

        print(f"\nWave best progress: {self.best_progress:.0f}%")


class BankSystem:
    def __init__(self) -> None:
        self.debt = 0.0
        self.credit_limit = 5000.0
        self.interest_rate = 0.10

    def money(self, amount: float) -> str:
        return f"${amount:,.2f}"

    def apply_interest(self) -> None:
        if self.debt > 0:
            interest = self.debt * self.interest_rate
            self.debt += interest
            print(f"\nBank interest added: {self.money(interest)}")

    def menu(self, bankroll: float) -> float:
        print("\n" + "=" * 48)
        print("                    BANK")
        print("=" * 48)
        print(f"Available balance: {self.money(bankroll)}")
        print(f"Outstanding debt: {self.money(self.debt)}")
        print(f"Credit limit: {self.money(self.credit_limit)}")
        print("1. Borrow money")
        print("2. Repay debt")
        print("3. Return to lobby")

        choice = input("Choose: ").strip().lower()
        if choice in ("1", "borrow", "b"):
            available = max(0.0, self.credit_limit - self.debt)
            if available <= 0:
                print("Your credit limit is exhausted.")
                return bankroll
            try:
                amount = float(input(f"Borrow amount (up to {self.money(available)}): ").strip())
            except ValueError:
                print("Enter a valid dollar amount.")
                return bankroll
            if amount < 1:
                print("Minimum loan is $1.")
            elif amount > available:
                print("That exceeds your available credit.")
            else:
                self.debt += amount
                bankroll += amount
                print(f"Loan issued: {self.money(amount)}")
        elif choice in ("2", "repay", "r"):
            if self.debt <= 0:
                print("You have no outstanding debt.")
            else:
                try:
                    amount = float(input(
                        f"Repay amount (up to {self.money(min(bankroll, self.debt))}): "
                    ).strip())
                except ValueError:
                    print("Enter a valid dollar amount.")
                    return bankroll
                amount = min(amount, bankroll, self.debt)
                if amount > 0:
                    bankroll -= amount
                    self.debt -= amount
                    print(f"Debt repaid: {self.money(amount)}")
                else:
                    print("Nothing was repaid.")
        return bankroll

    def collectors_game_over(self, bankroll: float) -> bool:
        if bankroll <= 0 and self.debt > 0:
            print("\n" + "=" * 48)
            print("          DEBT COLLECTORS ARRIVE")
            print("=" * 48)
            print("You lost all remaining funds with an unpaid loan.")
            print("As collateral, they repossess your casino winnings.")
            print("SESSION OVER")
            return True
        return False


class SewerTVFight:
    def run(self) -> float:
        print("\n" + "=" * 48)
        print("            SEWER TV — PRIME TIME")
        print("=" * 48)
        print("A fictional broadcast cuts in...")
        print("Batman: 'Audience, tonight's challenger is a Tibetan monk.'")
        print("Joker: 'And the sewer has terrible reception. Naturally.'")
        print("Monk: 'Mind is stronger than fists. Balance wins.'")

        health = 100
        monk_health = 100

        while health > 0 and monk_health > 0:
            print(f"\nYour TV fighter —  {health} HP")
            print(f"Tibetan monk —     {monk_health} HP")
            print("1. Strike")
            print("2. Dodge")
            print("3. Invite Batman and Joker to 'throw it back'")
            print("4. Leave the broadcast")
            choice = input("Choose: ").strip().lower()

            if choice in ("1", "strike"):
                damage = random.randint(12, 24)
                monk_health -= damage
                print(f"You land a clean TV-fight hit for {damage} damage.")
            elif choice in ("2", "dodge"):
                if random.random() < 0.65:
                    print("You dodge the monk's calm counterattack!")
                else:
                    damage = random.randint(8, 16)
                    health -= damage
                    print(f"The monk reads the feint and deals {damage} damage.")
            elif choice in ("3", "dance", "throw it back"):
                print("Batman throws it back. Joker throws it all the way back.")
                print("The crowd chants! The monk smiles and lowers his guard.")
                monk_health -= random.randint(5, 12)
            elif choice in ("4", "leave", "q"):
                print("You leave the sewer set.")
                break
            else:
                print("Choose a valid broadcast move.")
                continue

            if monk_health <= 0:
                break

            damage = random.randint(8, 18)
            health -= damage
            print(f"The monk counters gracefully for {damage} damage.")

        if monk_health <= 0:
            prize = random.randint(50, 250)
            print("\nKNOCKOUT!")
            print("Batman and Joker end the broadcast with one synchronized dance.")
            print(f"TV prize: ${prize:,.2f}")
            return prize
        if health <= 0:
            print("\nThe monk wins by composure.")
            return -25.0
        return 0.0

    def run_menu(self) -> None:
        print("\n" + "=" * 48)
        print("                 GEOMETRY DASH")
        print("=" * 48)
        print("1. Cube")
        print("2. Wave")
        print("3. Return to lobby")
        choice = input("Choose a mode: ").strip().lower()
        if choice in ("1", "cube", "c"):
            self.run()
        elif choice in ("2", "wave", "w"):
            self.run_wave()

    def run(self) -> None:
        print("\n" + "=" * 48)
        print("                 GEOMETRY DASH")
        print("=" * 48)
        print("Press SPACE to jump. Avoid spikes and reach 100%!")
        print("Press Q to return to the lobby.")
        input("Press Enter to begin...")

        try:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            in_raw_terminal = True
        except termios.error:
            old_settings = None
            in_raw_terminal = False

        try:
            while True:
                obstacles = {
                    13: "spike",
                    22: "spike",
                    31: "spike",
                    38: "double",
                    48: "spike",
                    57: "double",
                    68: "spike",
                    79: "double",
                    88: "spike",
                }
                player_y = 0
                vertical_speed = 0.0
                distance = 0
                won = False
                crashed = False

                print(f"\nAttempt {self.attempt} | Press SPACE")

                for distance in range(101):
                    key = "" if not in_raw_terminal else self.read_key(0.06)

                    if key.lower() == "q":
                        print("\nReturned to the lobby.")
                        return

                    if key == " " and player_y == 0:
                        vertical_speed = 2.2

                    player_y += vertical_speed
                    vertical_speed -= 0.42
                    if player_y <= 0:
                        player_y = 0
                        vertical_speed = 0

                    view_start = distance - 8
                    screen = []
                    for x in range(40):
                        world_x = view_start + x
                        obstacle = obstacles.get(world_x)
                        if obstacle and x < 40:
                            screen.append("^" if obstacle == "spike" else "^^")
                        else:
                            screen.append(" ")

                    player_x = 8
                    jump_height = min(int(round(player_y)), 3)

                    sys.stdout.write("\033[H\033[2J")
                    sys.stdout.write(f"ATTEMPT {self.attempt}  |  PROGRESS {distance}%\n")
                    sys.stdout.write("=" * 40 + "\n")
                    for row in range(3, -1, -1):
                        line = list(" " * 40)
                        if row == jump_height:
                            line[player_x] = "▲"
                        for x, tile in enumerate(screen):
                            if tile in ("^", "^^") and row == 0:
                                line[x] = "^"
                        sys.stdout.write("".join(line[:40]) + "\n")
                    sys.stdout.write("".join("_" for _ in range(40)) + "\n")
                    sys.stdout.flush()

                    obstacle = obstacles.get(distance)
                    if obstacle and jump_height == 0:
                        crashed = True
                        break

                    if distance >= 100:
                        won = True
                        break

                    time.sleep(0.06)

                progress = float(distance)
                if progress > self.best_progress:
                    self.best_progress = progress
                if progress > self.best_attempt:
                    self.best_attempt = int(progress)

                if won:
                    print("\nLEVEL COMPLETE!")
                    print("You reached 100%. Geometry Dash champion!")
                    break

                if crashed:
                    print(f"\nCRASHED at {distance}%.")
                    retry = input("Retry or lobby? (r/l): ").strip().lower()
                    if retry in ("l", "lobby", "q"):
                        break
                    self.attempt += 1

        finally:
            if old_settings is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()

        print(f"\nBest progress: {self.best_progress:.0f}%")


if __name__ == "__main__":
    bankroll = 1000.0
    bank = BankSystem()
    try:
        while bankroll >= 5 or bank.debt > 0:
            print("\n" + "=" * 48)
            print("                 CASINO LOBBY")
            print("=" * 48)
            print(f"Bankroll: {bankroll:,.2f}")
            print(f"Bank debt: ${bank.debt:,.2f}")
            print("1. Blackjack")
            print("2. European Roulette")
            print("3. Geometry Dash")
            print("4. Bank")
            print("5. Sewer TV Fight")
            print("6. Quit")
            choice = input("Choose a game: ").strip().lower()

            if choice in ("1", "blackjack", "b"):
                game = BlackjackGame()
                game.bankroll = bankroll
                bankroll = game.run()
                bank.apply_interest()
            elif choice in ("2", "roulette", "r"):
                bankroll = RouletteGame(bankroll).run()
                bank.apply_interest()
            elif choice in ("3", "geometry dash", "geometry", "gd"):
                GeometryDash().run_menu()
            elif choice in ("4", "bank"):
                bankroll = bank.menu(bankroll)
            elif choice in ("5", "sewer", "fight", "tv"):
                payout = SewerTVFight().run()
                bankroll += payout
                bank.apply_interest()
                print(f"Updated bankroll: ${bankroll:,.2f}")
            elif choice in ("6", "quit", "q"):
                break
            else:
                print("Please choose Blackjack, Roulette, Geometry Dash, Bank, or Quit.")

            if bank.collectors_game_over(bankroll):
                break
    except (KeyboardInterrupt, EOFError):
        print("\n\nThanks for visiting.")

    print(f"\nFinal session bankroll: ${bankroll:,.2f}")
