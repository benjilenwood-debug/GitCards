import random
import shlex
from enum import Enum, auto
from collections import deque, Counter

# =========================
# Card model
# =========================
class Suit(Enum):
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"

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

class CardType(Enum):
    NORMAL = auto()
    JOKER = auto()

class Card:
    def __init__(self, rank: Rank | None = None, suit: Suit | None = None, card_type: CardType = CardType.NORMAL):
        self.rank = rank
        self.suit = suit
        self.type = card_type

    # identity helpers
    def is_normal(self):
        return self.type == CardType.NORMAL

    def is_joker(self):
        return self.type == CardType.JOKER

    def copy(self):
        return Card(self.rank, self.suit, self.type)

    def __repr__(self):
        if self.type == CardType.JOKER:
            return "JK"
        rp = {Rank.A:"A", Rank.K:"K", Rank.Q:"Q", Rank.J:"J"}.get(self.rank, str(self.rank.value))
        return f"{rp}{self.suit.value}"

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.type == other.type and self.rank == other.rank and self.suit == other.suit

    def __hash__(self):
        return hash((self.type, self.rank, self.suit))

# Effective rank mapping: 8 and 9 are equivalent
# (Used for burn detection and comparing ranks under Means)
def effective_rank(r: Rank | None) -> Rank | None:
    if r in (Rank.EIGHT, Rank.NINE):
        return Rank.EIGHT
    return r

# =========================
# Deck utilities
# =========================
def build_common_deck() -> list[Card]:
    """Build the BASE GAME common deck:
    - Two full standard decks (52 × 2 = 104 normal cards)
    - Only TWO jokers total (not four).
    Then shuffle.
    """
    deck: list[Card] = []
    ranks = [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX, Rank.SEVEN,
             Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.J, Rank.Q, Rank.K, Rank.A]
    suits = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
    for _ in range(2):  # two decks
        for r in ranks:
            for s in suits:
                deck.append(Card(r, s))
    # only two jokers in the entire common deck
    deck.append(Card(card_type=CardType.JOKER))
    deck.append(Card(card_type=CardType.JOKER))
    random.shuffle(deck)
    return deck

# =========================
# Piles
# =========================
class CommonPile:
    def __init__(self):
        self.cards: list[Card] = []

    def top(self) -> Card | None:
        return self.cards[-1] if self.cards else None

    def add(self, cards: list[Card]):
        self.cards.extend(cards)

    def clear(self) -> list[Card]:
        pile = self.cards[:]
        self.cards.clear()
        return pile

    def detect_burns(self) -> dict[Rank, int]:
        """
        Count sets of four-of-a-kind by effective rank across the whole pile.
        2s and 3s are transparent separators: they do not contribute to a rank count
        and do not break counts of other ranks.
        8s and 9s are fused (effective rank 8).
        Returns {rank: count_of_burn_sets} (usually 0 or 1).
        """
        ctr: Counter[Rank] = Counter()
        for c in self.cards:
            if not c.is_normal():
                continue
            if c.rank in (Rank.TWO, Rank.THREE):
                continue  # transparent for burn counts
            ctr[effective_rank(c.rank)] += 1
        burns: dict[Rank, int] = {}
        for r, n in ctr.items():
            if n >= 4:
                burns[r] = n // 4
        return burns

    def view_line_for_board(self) -> list[str]:
        # Show top at col 7; same-rank behind to the right if any (up to two previews)
        row = ["0"] * 13
        if not self.cards:
            row[6] = "X"  # placeholder when empty
            return row
        top = self.cards[-1]
        row[6] = repr(top)
        # show previous same-effective-rank cards immediately behind (right side)
        shown = 0
        i = len(self.cards) - 2
        while i >= 0 and shown < 2:
            c = self.cards[i]
            if c.is_normal() and top.is_normal() and effective_rank(c.rank) == effective_rank(top.rank):
                row[8 + shown*2] = repr(c)
                shown += 1
            elif c.is_normal() and c.rank in (Rank.TWO, Rank.THREE):
                # also show 2s and 3s (rule: always visible in the trail)
                row[8 + shown*2] = repr(c)
                shown += 1
            i -= 1
        return row

    def __repr__(self):
        return f"Pile:{self.cards}"

# =========================
# Player
# =========================
class Player:
    def __init__(self, name: str):
        self.name = name
        self.hand: list[Card] = []
        self.face_up: list[Card] = []  # exactly 3 once chosen
        self.face_down: list[Card] = []  # exactly 3 (unknown to opponent; middle peeked)
        self.known_middle_fd: Card | None = None  # what the owner saw during setup
        self.personal_pile: deque[Card] = deque()  # replenishes hand
        # Status
        self.has_status: bool = False

    def max_hand(self) -> int:
        return 5 if self.has_status else 4

    def replenish(self):
        # draw from personal pile until reaching max hand size
        while len(self.hand) < self.max_hand() and self.personal_pile:
            self.hand.append(self.personal_pile.popleft())

    def all_cards_empty(self) -> bool:
        return (not self.personal_pile) and (not self.hand) and (not self.face_up) and (not self.face_down)

    def remove_from_zones(self, card: Card) -> bool:
        # remove exactly one copy of 'card' from hand or face_up (legal play zones)
        for zone in (self.hand, self.face_up):
            for i, c in enumerate(zone):
                if c.is_joker() and card.is_joker():
                    zone.pop(i)
                    return True
                if c.is_normal() and card.is_normal() and c.rank == card.rank and c.suit == card.suit:
                    zone.pop(i)
                    return True
        return False

    def has_block_piece(self) -> bool:
        # has any 4 or a Joker in hand to block a JK action
        return any((c.is_joker() or (c.is_normal() and c.rank == Rank.FOUR)) for c in self.hand)

    def take_pile_into_hand(self, cards: list[Card]):
        self.hand.extend(cards)

    def __repr__(self):
        return f"{self.name} | Hand:{self.hand} | FU:{self.face_up} | FD:{['??' for _ in self.face_down]} | Pile:{len(self.personal_pile)} | Status:{'Y' if self.has_status else 'N'}"

# =========================
# Game State
# =========================
class GameState:
    def __init__(self, players: list[Player]):
        self.players = players
        self.current_idx = 0
        self.common_pile = CommonPile()
        # Means (descending) state
        self.means_active = False
        self.means_limit: Rank | None = None  # next plays must be LOWER than this rank when active
        # Status token
        self.first_burn = False
        self.status_rank: Rank | None = None

    # --- Turn helpers ---
    def current(self) -> Player:
        return self.players[self.current_idx]

    def opponent(self) -> Player:
        return self.players[1 - self.current_idx]

    def advance(self):
        self.current_idx = 1 - self.current_idx

    # --- Status ---
    def set_status_on_first_burn(self, player: Player, burn_rank: Rank):
        if not self.first_burn:
            self.first_burn = True
            self.status_rank = burn_rank
            player.has_status = True

    def transfer_status_due_to_means(self, attacker: Player, defender: Player):
        # If defender currently has status and attacker plays a means card, status transfers
        if defender.has_status:
            defender.has_status = False
            attacker.has_status = True

    # --- Rules / legality ---
    def legal_under_means(self, cards: list[Card], via_pair: bool) -> bool:
        if via_pair:
            # 3+same-suit pair or 2+{5/7/A} combo overrides constraints
            return True
        if not self.means_active:
            return True
        # must be lower than the means_limit for normal cards; 3 alone is allowed but inherits constraint (no change)
        for c in cards:
            if c.is_normal():
                r = effective_rank(c.rank)
                if r == Rank.THREE:
                    # 3 alone is okay (inherits), but if accompanied by other non-3 normals, check them too
                    continue
                if self.means_limit and r.value >= effective_rank(self.means_limit).value:
                    return False
        return True

    def resolve_burns_if_any(self, player: Player, msgs: list[str]):
        burns = self.common_pile.detect_burns()
        if not burns:
            return
        # In BASE GAME we just resolve all burns we find in arbitrary order (no emergency rows)
        for r, count in burns.items():
            for i in range(count):
                self.set_status_on_first_burn(player, r)
                msgs.append(f"Burn! Four {r.name}s. Clearing pile.")
                self.common_pile.clear()
                # Reset means state after a burn
                self.means_active = False
                self.means_limit = None

    def play(self, player: Player, raw_cards: list[Card], via_pair: bool = False) -> tuple[list[str], bool]:
        msgs: list[str] = []
        opp = self.opponent()

        # Validate zone: player must play from hand while they have cards in hand; once empty, may use face_up; once empty, face_down blind
        # For BASE GAME we allow selecting from hand or face_up; face_down plays are via special tokens (FD1/FD2/FD3) handled in parser
        # Validate possession
        for rc in raw_cards:
            # raw_cards may contain a special marker (string) if face-down chosen – handled in parser to flip into a real card
            if not isinstance(rc, Card):
                continue
            if rc not in player.hand and rc not in player.face_up:
                return [f"{player.name} does not have {rc} in a playable zone"], False

        # JK must be played alone for this BASE GAME
        if any(c.is_joker() for c in raw_cards) and len(raw_cards) != 1:
            return ["Joker must be played alone in base game."], False

        # Means legality check
        if not self.legal_under_means([c for c in raw_cards if isinstance(c, Card)], via_pair):
            return ["Illegal under current means: next card must be lower."], False

        # Remove from zones
        played: list[Card] = []
        for rc in raw_cards:
            if not isinstance(rc, Card):
                continue
            if player.remove_from_zones(rc):
                played.append(rc)

        # Add to pile
        self.common_pile.add(played)
        msgs.append(f"{player.name} played {played}.")

        # Means activation: if a 5 or 7 was played (or 2+{5/7} same-suit combo was used -> flagged by via_pair_with_means)
        via_pair_with_means = False
        if via_pair:
            # If the pair contains a 5 or 7 and the suits of the 2 and (5/7) match, the means applies (descend)
            ranks = [c.rank for c in played if c.is_normal()]
            suits = [c.suit for c in played if c.is_normal()]
            if Rank.TWO in ranks and (Rank.FIVE in ranks or Rank.SEVEN in ranks) and len(set(suits)) == 1:
                via_pair_with_means = True
        has_means_card = any(c.is_normal() and c.rank in (Rank.FIVE, Rank.SEVEN) for c in played)
        if has_means_card or via_pair_with_means:
            # status transfer if defender held it
            self.transfer_status_due_to_means(player, opp)
            # activate means (next plays must be lower than the anchor rank = last means rank in this play)
            anchor = None
            for c in reversed(played):
                if c.is_normal() and c.rank in (Rank.FIVE, Rank.SEVEN):
                    anchor = c.rank
                    break
            if via_pair_with_means and anchor is None:
                anchor = Rank.FIVE if any(c.rank == Rank.FIVE for c in played if c.is_normal()) else Rank.SEVEN
            self.means_active = True
            self.means_limit = anchor
            msgs.append(f"Means in effect: next card must be lower than {anchor.name}.")
        else:
            # Non-means play breaks means
            self.means_active = False
            self.means_limit = None

        # Resolve burns (can reset means + create status on first burn)
        self.resolve_burns_if_any(player, msgs)

        # JK offense resolution (force pickup unless blocked by a 4 or a JK)
        if played and played[-1].is_joker():
            msgs.append(f"{player.name} used a Joker: attempting to force {opp.name} to pick up the pile.")
            if opp.has_block_piece():
                choice = input(f"{opp.name}, block with a 4 or JK? (type e.g. 4S, 4H, JK or 'no'): ").strip().upper()
                if choice == "JK":
                    # consume one JK from defender hand
                    for i, c in enumerate(opp.hand):
                        if c.is_joker():
                            opp.hand.pop(i)
                            msgs.append(f"{opp.name} blocked with JK.")
                            break
                elif len(choice) == 2 and choice[0] == '4' and choice[1] in "SHDC":
                    suit_map = {"S": Suit.SPADES, "H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS}
                    target = Card(Rank.FOUR, suit_map[choice[1]])
                    if target in opp.hand:
                        opp.hand.remove(target)
                        msgs.append(f"{opp.name} blocked with {target}.")
                    else:
                        msgs.append(f"{opp.name} tried to block with {target} but doesn't have it. Force succeeds.")
                        self._force_pickup(opp, msgs)
                else:
                    msgs.append(f"{opp.name} did not block. Force succeeds.")
                    self._force_pickup(opp, msgs)
            else:
                self._force_pickup(opp, msgs)

        # Win check
        win = player.all_cards_empty()
        return msgs, win

    def _force_pickup(self, defender: Player, msgs: list[str]):
        if self.common_pile.cards:
            pile_cards = self.common_pile.clear()
            defender.take_pile_into_hand(pile_cards)
            msgs.append(f"{defender.name} picked up the pile ({len(pile_cards)} card(s)).")
        # breaking means after a pickup keeps current means unless we decide otherwise – for BASE GAME, clear it for simplicity
        self.means_active = False
        self.means_limit = None

    # =========================
    # Rendering (board: 9 rows × 13 cols)
    # =========================
    def _row_hand(self, viewer: Player, owner: Player) -> list[str]:
        row = ["0"] * 13
        # hand visible only to owner
        if owner is viewer:
            for i, c in enumerate(owner.hand[:11]):
                row[i] = repr(c)
        else:
            for i, _ in enumerate(owner.hand[:11]):
                row[i] = "X"
        # last two cells show personal pile count as 2-digit number
        pile_n = len(owner.personal_pile)
        row[11] = str(pile_n // 10)
        row[12] = str(pile_n % 10)
        return row

    def _row_emergency_placeholder(self) -> list[str]:
        # base game: no emergencies — leave empty/zeros; keep first cell as 'X' placeholder like doc examples
        row = ["0"] * 13
        row[0] = "X"
        return row

    def _row_face(self, viewer: Player, owner: Player, top_row: bool) -> list[str]:
        # positions: face-down at [0,1,2]; face-up at [4,6,8]; status at [12]
        row = ["0"] * 13
        # face-down
        for idx in range(3):
            if idx < len(owner.face_down):
                # middle known to owner
                if idx == 1 and owner.known_middle_fd is not None and viewer is owner:
                    row[idx] = repr(owner.known_middle_fd)
                else:
                    row[idx] = "X" if (viewer is not owner) else "U"
        # face-up (visible to both)
        for j, pos in enumerate([4, 6, 8]):
            if j < len(owner.face_up):
                row[pos] = repr(owner.face_up[j])
        # status
        if self.first_burn:
            # show letter for holder, 0 for non-holder
            if owner.has_status:
                row[12] = self._status_token_text()
            else:
                row[12] = "0"
        else:
            row[12] = "S"  # placeholder before first burn
        return row

    def _status_token_text(self) -> str:
        if not self.status_rank:
            return "S"
        return {Rank.A:"A", Rank.K:"K", Rank.Q:"Q", Rank.J:"J"}.get(self.status_rank, str(self.status_rank.value))

    def board_rows_for_viewer(self, viewer: Player) -> list[list[str]]:
        rows: list[list[str]] = []
        # Row 1: P1 hand
        rows.append(self._row_hand(viewer, self.players[0]))
        # Row 2: P1 emergency placeholder
        rows.append(self._row_emergency_placeholder())
        # Row 3: P1 face down/up + status
        rows.append(self._row_face(viewer, self.players[0], top_row=True))
        # Row 4: Red pile placeholder (unused)
        r4 = ["0"] * 13
        r4[0] = "R"
        rows.append(r4)
        # Row 5: Common pile (center)
        rows.append(self.common_pile.view_line_for_board())
        # Row 6: Blue pile placeholder (unused)
        r6 = ["0"] * 13
        r6[0] = "B"
        rows.append(r6)
        # Row 7: P2 face down/up + status
        rows.append(self._row_face(viewer, self.players[1], top_row=False))
        # Row 8: P2 emergency placeholder
        rows.append(self._row_emergency_placeholder())
        # Row 9: P2 hand
        rows.append(self._row_hand(viewer, self.players[1]))
        return rows

    def render_for(self, viewer: Player) -> str:
        rows = self.board_rows_for_viewer(viewer)
        return "\n".join(" ".join(r) for r in rows)

    def __repr__(self):
        # default repr from current player's POV
        return self.render_for(self.current())

# =========================
# Parsing helpers
# =========================
SUIT_BY_CHAR = {"S": Suit.SPADES, "H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS}
RANK_BY_CHAR = {"A": Rank.A, "K": Rank.K, "Q": Rank.Q, "J": Rank.J,
                 "10": Rank.TEN, "9": Rank.NINE, "8": Rank.EIGHT, "7": Rank.SEVEN,
                 "6": Rank.SIX, "5": Rank.FIVE, "4": Rank.FOUR, "3": Rank.THREE, "2": Rank.TWO}


def parse_single_card(tok: str) -> Card:
    t = tok.strip().upper()
    if t == "JK":
        return Card(card_type=CardType.JOKER)
    # match e.g. 10S, 7C, AS
    # split last char as suit, rest as rank
    if len(t) < 2:
        raise ValueError("Bad card token")
    suit_ch = t[-1]
    rank_str = t[:-1]
    if suit_ch not in SUIT_BY_CHAR:
        raise ValueError("Bad suit")
    if rank_str not in RANK_BY_CHAR:
        # allow single-letter ranks like T for 10? no; require 10
        raise ValueError("Bad rank")
    return Card(RANK_BY_CHAR[rank_str], SUIT_BY_CHAR[suit_ch])


def parse_cards_arg(arg: str) -> tuple[list[Card], bool]:
    """Parse a play-argument which can be:
    - comma separated list: "2H, 7C"
    - multiplier: "3x8" (plays any 3 eights from zones choosing suits automatically is not supported; user must specify suits) -> we'll reject
    - plus pair: "3C+QC" or "2S+5S" etc (flags via_pair=True)
    For BASE GAME we support list and plus pair. Multipliers require explicit suits per copy.
    Returns (cards, via_pair)
    """
    via_pair = False
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    cards: list[Card] = []
    for p in parts:
        if "+" in p:
            # pair sequence – all pieces parsed, flagged as via_pair
            subs = [s.strip() for s in p.split("+") if s.strip()]
            sub_cards = [parse_single_card(s) for s in subs]
            cards.extend(sub_cards)
            via_pair = True
        else:
            cards.append(parse_single_card(p))
    return cards, via_pair

# =========================
# Setup & CLI
# =========================

def deal_base_game(p1: Player, p2: Player):
    deck = build_common_deck()
    # split evenly into two personal piles (random who gets the extra)
    half = len(deck) // 2
    extra_first = random.choice([True, False])
    if extra_first:
        p1.personal_pile = deque(deck[:half + 1])
        p2.personal_pile = deque(deck[half + 1:])
    else:
        p1.personal_pile = deque(deck[:half])
        p2.personal_pile = deque(deck[half:])

    # Face-down: take 3 unknown from personal pile
    for pl in (p1, p2):
        for _ in range(3):
            pl.face_down.append(pl.personal_pile.popleft())
        # Each player peeks their middle card (index 1)
        pl.known_middle_fd = pl.face_down[1]

    # Initial hands: draw 8
    for pl in (p1, p2):
        for _ in range(8):
            pl.hand.append(pl.personal_pile.popleft())

    # Let each player choose 3 face-up cards from their hand to place on top of the 3 face-down
    for pl in (p1, p2):
        print(f"\n{pl.name}, choose 3 face-up cards from your hand (e.g., 'AS, 7C, 4H'):")
        print(f"Your hand: {pl.hand}")
        while True:
            try:
                sel = input("> ").strip()
                up_cards, _ = parse_cards_arg(sel) if sel else ([], False)
                if len(up_cards) != 3:
                    raise ValueError("Please select exactly 3 cards.")
                # verify ownership
                tmp = pl.hand[:]
                for c in up_cards:
                    if c in tmp:
                        tmp.remove(c)
                    else:
                        raise ValueError(f"You don't have {c}.")
                # commit
                for c in up_cards:
                    pl.hand.remove(c)
                pl.face_up = up_cards
                break
            except Exception as e:
                print(f"Invalid selection: {e}")
                print(f"Your hand: {pl.hand}")

    # After setup, top-of-turn player is random
    return


def print_board(game: GameState):
    print(game.render_for(game.current()))


def process_command(game: GameState, raw: str) -> tuple[list[str], bool]:
    tokens = shlex.split(raw)
    if not tokens:
        return ["Empty command"], False
    cmd = tokens[0].lower()
    pl = game.current()
    if cmd == "help":
        return [
            "Commands:",
            "  play <cards>        e.g., play 7C | play 2H, 2D | play 3C+QC | play 2S+5S",
            "  pickup              take the center pile into your hand",
            "  status              show status token holder",
            "  view hand|board     inspect",
            "  quit                exit game",
        ], False

    if cmd == "view":
        if len(tokens) < 2:
            return ["Specify 'hand' or 'board'"], False
        t = tokens[1].lower()
        if t == "hand":
            return [f"{pl.name} hand: {pl.hand}"], False
        if t == "board":
            return [game.render_for(pl)], False
        return ["Unknown view target"], False

    if cmd == "status":
        holder_lines = []
        for p in game.players:
            tok = game._status_token_text() if p.has_status else ("0" if game.first_burn else "S")
            holder_lines.append(f"{p.name}: status={tok}")
        return holder_lines, False

    if cmd == "pickup":
        if not game.common_pile.cards:
            return ["Nothing to pick up"], False
        cards = game.common_pile.clear()
        pl.take_pile_into_hand(cards)
        return [f"{pl.name} picked up the pile ({len(cards)} card(s))."], False

    if cmd == "play":
        if len(tokens) < 2:
            return ["Usage: play <cards>"], False
        try:
            arg = raw.split(" ", 1)[1]
            cards, via_pair = parse_cards_arg(arg)
        except Exception as e:
            return [f"Parse error: {e}"], False
        msgs, win = game.play(pl, cards, via_pair)
        return msgs, win

    if cmd in ("quit", "exit"):
        return ["quit"], True

    return ["Unknown command (type 'help')"], False


# =========================
# Run loop
# =========================

def run_base_game():
    print("BASE GAME — simplified two‑player CLI")
    p1 = Player(input("Enter Player 1 name: ") or "P1")
    p2 = Player(input("Enter Player 2 name: ") or "P2")
    game = GameState([p1, p2])

    # Deal & setup
    deal_base_game(p1, p2)

    # Randomize starting player
    game.current_idx = random.choice([0, 1])

    # Initial replenish to max (status not present yet → 4)
    for pl in (p1, p2):
        pl.replenish()

    # Loop
    while True:
        print("\n============================")
        print(f"{game.current().name}'s turn")
        print_board(game)
        if game.means_active and game.means_limit:
            print(f"Means active: next card must be lower than {game.means_limit.name}.")
        raw = input(f"{game.current().name}> ").strip()
        msgs, flag = process_command(game, raw)
        if msgs and msgs[0] == "quit":
            print("Goodbye!")
            break
        for m in msgs:
            print(m)
        # Win?
        if flag:
            print(f"{game.current().name} wins! 🎉")
            break
        # Replenish current player, then pass turn
        game.current().replenish()
        game.advance()


if __name__ == "__main__":
    run_base_game()
