
import random
from enum import Enum, auto
from collections import deque, Counter
import shlex

# ANSI colors for CLI rendering
class Color:
    RED = "\033[31m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

# Card suits
class Suit(Enum):
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"

# Card ranks
class Rank(Enum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    J = 11
    Q = 12
    K = 13
    A = 14

def effective_rank(rank):
    """Treat 8 and 9 as equivalent for burns."""
    if rank in (Rank.EIGHT, Rank.NINE):
        return Rank.EIGHT
    return rank

# Card types
class CardType(Enum):
    NORMAL = auto()
    JOKER = auto()
    PFJ = auto()
    FRE = auto()
    EMERGENCY_RED = auto()
    EMERGENCY_BLUE = auto()

# Card representation
class Card:
    def __init__(self, rank=None, suit=None, card_type=CardType.NORMAL):
        self.rank = rank
        self.suit = suit
        self.type = card_type
        self.just_acquired = False  # flag for emergency restrictions

    def __repr__(self):
        if self.type == CardType.JOKER:
            return "JK"
        if self.type == CardType.PFJ:
            return "PFJ"
        if self.type == CardType.FRE:
            return "FRE"
        if self.type == CardType.EMERGENCY_RED:
            return "RED"
        if self.type == CardType.EMERGENCY_BLUE:
            return "BLUE"
        # normal card
        rank_map = {Rank.A: "A", Rank.J: "J", Rank.Q: "Q", Rank.K: "K"}
        r = rank_map.get(self.rank, str(self.rank.value))
        return f"{r}{self.suit.value}"

    def is_normal(self):
        return self.type == CardType.NORMAL

    def equivalent_for_burn(self, other):
        if not self.is_normal() or not other.is_normal():
            return False
        return effective_rank(self.rank) == effective_rank(other.rank)

    def copy(self):
        c = Card(self.rank, self.suit, self.type)
        c.just_acquired = self.just_acquired
        return c

# Deck of cards
class Deck:
    def __init__(self):
        self.cards = deque()
        self.build()
        self.shuffle()

    def build(self):
        self.cards.clear()
        for suit in Suit:
            for rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX,
                         Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.J,
                         Rank.Q, Rank.K, Rank.A]:
                self.cards.append(Card(rank, suit))

    def shuffle(self):
        temp = list(self.cards)
        random.shuffle(temp)
        self.cards = deque(temp)

    def draw(self, n=1):
        drawn = []
        for _ in range(n):
            if self.cards:
                drawn.append(self.cards.popleft())
        return drawn

# Common pile in center
class CommonPile:
    def __init__(self):
        self.cards = []
        self.consumed = set()  # track consumed 2s/3s if needed

    def add(self, cards):
        self.cards.extend(cards)

    def clear(self):
        temp = self.cards[:]
        self.cards = []
        self.consumed.clear()
        return temp

    def top(self):
        return self.cards[-1] if self.cards else None

    def detect_burns(self):
        ctr = Counter()
        for c in self.cards:
            if c.is_normal() and c.rank not in (Rank.TWO, Rank.THREE):
                ctr[effective_rank(c.rank)] += 1
        burns = {rank: cnt//4 for rank, cnt in ctr.items() if cnt >= 4}
        return burns

    def __repr__(self):
        return f"{self.cards}"

# Player state
class Player:
    def __init__(self, name):
        self.name = name
        self.hand = []
        self.face_up = []
        self.face_down = []
        self.emergency_red = []
        self.emergency_blue = []
        self.personal_pile = []
        self.status_token = None
        self.has_status_ability = False
        self.can_replenish_full = False
        self.emergency_actions = {}  # id(card): {'peek':bool,'swap':bool}

    def hand_limit(self):
        return 5 if self.has_status_ability else 4

    def needs_replenish(self):
        return len(self.hand) < (self.hand_limit() if self.has_status_ability else 4)

    def pickup_common(self, cards):
        self.hand.extend(cards)
        self.personal_pile = []

    def replenish(self):
        while self.needs_replenish() and self.personal_pile:
            self.hand.append(self.personal_pile.pop(0))

    def reset_emergency_actions(self):
        self.emergency_actions.clear()
        for c in self.emergency_red + self.emergency_blue:
            self.emergency_actions[id(c)] = {'peek': True, 'swap': True}

    def __repr__(self):
        sd = self.status_token.name if self.status_token else ("S" if not self.has_status_ability else "0")
        fd = ["??"]*len(self.face_down)
        return (f"{self.name} | Hand:{self.hand} | Up:{self.face_up} | Down:{fd} "
                f"| S:{sd} | Red:{self.emergency_red} | Blue:{self.emergency_blue} "
                f"| Pile:{len(self.personal_pile)}")

# Full game logic
class GameState:
    def __init__(self, players, interactive=True):
        self.common_pile = CommonPile()
        self.players = players
        self.current_idx = 0
        self.first_burn = False
        self.status_rank = None
        self.offenses = []  # list of pending joker/PFJ sub-actions
        self.interactive = interactive

    def current(self):
        return self.players[self.current_idx]

    def opponent(self):
        return self.players[1-self.current_idx]

    def advance(self):
        self.current_idx = 1 - self.current_idx

    def set_status(self, player, rank):
        if not self.first_burn:
            self.first_burn = True
            self.status_rank = rank
            player.status_token = rank
            player.has_status_ability = True

    def transfer_status(self, src, tgt):
        if tgt.has_status_ability:
            tgt.has_status_ability = False
            tgt.status_token = None
            src.has_status_ability = True
            src.status_token = self.status_rank

    def resolve_burns(self, player, msgs):
        burns = self.common_pile.detect_burns()
        if not burns:
            return
        ranks = list(burns.keys())
        order = ranks
        if self.interactive and len(ranks) > 1:
            print(f"Multiple burns detected: {ranks}")
            choice = input(f"{player.name}, resolve in what order? ").split(",")
            cleaned = [c.strip().upper() for c in choice]
            order = [r for r in ranks if r.name in cleaned] or ranks
        for r in order:
            for i in range(burns[r]):
                self.set_status(player, r)
                msgs.append(f"Burn: {r.name}({i+1}), clearing pile.")
                self.common_pile.clear()
                nb = Card(card_type=CardType.EMERGENCY_BLUE)
                nb.just_acquired = True
                player.emergency_blue.append(nb)
                msgs.append(f"{player.name} gained blue emergency.")
                player.reset_emergency_actions()
                # disable actions on new
                player.emergency_actions[id(nb)] = {'peek': False, 'swap': False}
                self.emergency_prompt(player, msgs)

    def emergency_prompt(self, player, msgs):
        for c in player.emergency_red + player.emergency_blue:
            aid = id(c)
            avail = player.emergency_actions.get(aid, {})
            if c.just_acquired:
                continue
            if avail.get('peek') and self.interactive:
                ch = input(f"{player.name}, peek {c}? (y/n) ").lower()
                if ch == 'y':
                    msgs.append(f"{player.name} peeked at {c}.")
                    player.emergency_actions[aid]['peek'] = False
            if avail.get('swap') and self.interactive:
                ch = input(f"{player.name}, swap {c}? (y/n) ").lower()
                if ch == 'y':
                    new = Card(card_type=c.type)
                    new.just_acquired = True
                    if c.type == CardType.EMERGENCY_RED:
                        idx = player.emergency_red.index(c)
                        player.emergency_red[idx] = new
                    else:
                        idx = player.emergency_blue.index(c)
                        player.emergency_blue[idx] = new
                    msgs.append(f"{player.name} swapped emergency {c}.")
                    player.emergency_actions[aid]['swap'] = False

    def play(self, player, cards, via_pair=False):
        msgs = []
        win = False
        opp = self.opponent()
        # remove from hand
        for c in cards:
            if c in player.hand:
                player.hand.remove(c)
        # FRE
        for c in cards:
            if c.type == CardType.FRE:
                nr = Card(card_type=CardType.EMERGENCY_RED)
                nr.just_acquired = True
                player.emergency_red.append(nr)
                msgs.append(f"{player.name} played FRE: gained red emergency.")
                player.reset_emergency_actions()
                player.emergency_actions[id(nr)] = {'peek': False, 'swap': False}
        # Means logic
        has_means = any(c.is_normal() and c.rank in (Rank.FIVE, Rank.SEVEN) for c in cards)
        if has_means and opp.has_status_ability:
            self.transfer_status(player, opp)
            msgs.append(f"Status transferred to {player.name} due to means.")
        if has_means:
            player.can_replenish_full = True
            opp.can_replenish_full = True
        if via_pair:
            player.can_replenish_full = False
        # add to pile
        self.common_pile.add(cards)
        msgs.append(f"{player.name} played {cards}.")
        # TEN wipe
        if len(cards) == 1 and cards[0].is_normal() and cards[0].rank == Rank.TEN:
            self.common_pile.clear()
            msgs.append(f"{player.name} played TEN: pile wiped.")
        # PFJ
        for c in cards:
            if c.type == CardType.PFJ:
                if opp.personal_pile:
                    player.personal_pile.extend(opp.personal_pile)
                    opp.personal_pile = []
                    msgs.append(f"{player.name} used PFJ: stole personal pile.")
                else:
                    msgs.append(f"{player.name} used PFJ: strength-1 effect.")
        # Joker offense
        jks = [c for c in cards if c.type == CardType.JOKER]
        if jks:
            self.offenses.append({'att': player, 'str': len(jks), 'res': False})
            msgs.append(f"{player.name} initiated joker offense strength {len(jks)}.")
        # Burns
        self.resolve_burns(player, msgs)
        # Win check
        if not (player.hand or player.face_up or player.face_down or player.personal_pile):
            msgs.append(f"{player.name} wins!")
            win = True
        return msgs, win

    def resolve_offenses(self):
        msgs = []
        for action in list(self.offenses):
            if action['res']:
                continue
            pl = action['att']
            df = self.opponent() if self.current() == pl else self.current()
            req = action['str']
            prov = 0
            used = []
            for c in list(df.hand):
                if prov >= req:
                    break
                if c.type == CardType.JOKER or (c.is_normal() and c.rank == Rank.FOUR) or c.type == CardType.PFJ:
                    prov += 1
                    used.append(c)
            if prov >= req:
                to_cons = req
                consumed = []
                for c in used:
                    if to_cons <= 0:
                        break
                    if c in df.hand:
                        df.hand.remove(c)
                        consumed.append(c)
                        to_cons -= 1
                msgs.append(f"{df.name} blocked with {consumed}.")
            else:
                msgs.append(f"Block insufficient ({prov}<{req}); {pl.name}'s offense succeeds.")
                if self.common_pile.cards:
                    df.pickup_common(self.common_pile.clear())
                    msgs.append(f"{pl.name} forced {df.name} to pick up.")
            action['res'] = True
        self.offenses = [a for a in self.offenses if not a['res']]
        return msgs

    def __repr__(self):
        return f"Pile: {self.common_pile}\n{self.players[0]}\n{self.players[1]}"

def parse_card(tok):
    t = tok.upper()
    if t == "JK":
        return Card(card_type=CardType.JOKER)
    if t == "PFJ":
        return Card(card_type=CardType.PFJ)
    if t == "FRE":
        return Card(card_type=CardType.FRE)
    rp, sc = t[:-1], t[-1]
    suit = next((s for s in Suit if s.value == sc), None)
    if not suit:
        raise ValueError(f"Invalid suit: {sc}")
    if rp == "A":
        r = Rank.A
    elif rp == "J":
        r = Rank.J
    elif rp == "Q":
        r = Rank.Q
    elif rp == "K":
        r = Rank.K
    else:
        r = Rank(int(rp))
    return Card(r, suit)

def process_command(game, cmd):
    tokens = shlex.split(cmd)
    if not tokens:
        return ["Empty command"], False
    pl = game.current()
    pm = tokens[0].lower()
    msgs = []
    win = False
    if pm == "play":
        cards = []
        via_pair = False
        for tok in tokens[1:]:
            if "+" in tok:
                parts = tok.split("+")
                combo = [parse_card(p) for p in parts]
                cards.extend(combo)
                suits = [c.suit for c in combo if c.is_normal()]
                ranks = [c.rank for c in combo if c.is_normal()]
                if any(r == Rank.THREE for r in ranks) and len(set(suits)) == 1:
                    via_pair = True
            else:
                cards.append(parse_card(tok))
        for c in cards:
            if c not in pl.hand:
                return [f"{pl.name} does not have {c}"], False
        msgs, win = game.play(pl, cards, via_pair)
        msgs += game.resolve_offenses()
        if not win:
            game.advance()
        return msgs, win
    if pm.startswith("burn"):
        try:
            part = cmd.split(",", 1)[1]
            rp, cp = part.split("x")
            cp = int(cp)
            rp = rp.strip().upper()
            if rp == "A":
                r = Rank.A
            elif rp == "J":
                r = Rank.J
            elif rp == "Q":
                r = Rank.Q
            elif rp == "K":
                r = Rank.K
            else:
                r = Rank(int(rp))
        except:
            return ["Invalid burn syntax"], False
        cards = [Card(r, random.choice(list(Suit))) for _ in range(cp)]
        msgs, win = game.play(pl, cards)
        msgs += game.resolve_offenses()
        if not win:
            game.advance()
        return msgs, win
    if pm == "pickup":
        if not game.common_pile.cards:
            return ["Nothing to pick up"], False
        cards = game.common_pile.clear()
        pl.pickup_common(cards)
        return [f"{pl.name} picked up pile"], False
    if pm == "status":
        for p in game.players:
            tok = p.status_token.name if p.status_token else ("0" if game.first_burn else "S")
            msgs.append(f"{p.name}: status={tok}")
        return msgs, False
    if pm == "view":
        if len(tokens) < 2:
            return ["Specify view target"], False
        t = tokens[1].lower()
        if t == "board":
            return [repr(game)], False
        if t == "hand":
            return [f"{pl.name} hand: {pl.hand}"], False
        if t == "common":
            return [f"Pile: {game.common_pile.cards}"], False
        return ["Unknown view target"], False
    return ["Unknown command"], False

def render_board(game):
    print(repr(game))

def run_demo():
    p1 = Player("Alice")
    p2 = Player("Bob")
    game = GameState([p1, p2], interactive=True)
    deck = Deck()
    p1.hand = deck.draw(5)
    p2.hand = deck.draw(5)
    p1.face_down = deck.draw(3)
    p2.face_down = deck.draw(3)
    p1.face_up = deck.draw(2)
    p2.face_up = deck.draw(2)
    while True:
        render_board(game)
        cmd = input(f"{game.current().name}> ").strip()
        if cmd.lower() in ("quit", "exit"):
            break
        msgs, win = process_command(game, cmd)
        for m in msgs:
            print(m)
        if win:
            print(f"{game.current().name} wins!")
            break
        game.current().replenish()
        game.advance()

if __name__ == "__main__":
    run_demo()
