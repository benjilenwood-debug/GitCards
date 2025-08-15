import random
# random: Provides random number functions.
# - Used to shuffle decks, deal cards randomly, pick a random player, etc.
# Common functions:
#   random.shuffle(list)      → Shuffles a list in-place (e.g., deck of cards).
#   random.choice(list)       → Picks one random element from a list.
#   random.randint(a, b)      → Random int between a and b, inclusive.
from enum import Enum, auto
# Enum: Lets you create enumerations — fixed sets of named constants.
#   Example: class Suit(Enum): SPADES = "S"; HEARTS = "H"
#   Benefits: Prevents typos, makes code easier to read, works well with autocomplete.
# auto(): Auto-assigns values to Enum members so you don't have to specify them manually.
#   Example: class Rank(Enum): ACE = auto(); TWO = auto()
from collections import deque, Counter
# deque: A "double-ended queue".
# - Like a list but optimised for adding/removing from both ends (O(1) speed).
# - Perfect for a draw pile where cards are taken from the top and added to the bottom.
#   Methods: append(), appendleft(), pop(), popleft()
# Counter: A dictionary subclass for counting items.
# - Great for tallying cards in a hand, counting suits, or tracking how many cards remain of a rank.
#   Example: Counter(['A','K','A']) → {'A': 2, 'K': 1}
import shlex
# shlex: Shell-like lexical parsing of strings.
# - Splits player commands into tokens while respecting quotes.
# - Useful if you let players type card names with spaces (e.g., "Ace of Spades").
#   Example: shlex.split('play "Ace of Spades" face-up')
#            → ['play', 'Ace of Spades', 'face-up']

# ANSI Color definitions for CLI
class Color:
    RED = "\033[31m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


#  Defines an enumeration (Enum) for the four card suits.
#   • Comparison:      if suit == Suit.HEARTS: ...
#   • Iteration:       for s in Suit: ...
#   • Conversion:      Suit("H") -> Suit.HEARTS  (invalid values raise ValueError)
#   • Introspection:   s.name  -> "HEARTS",  s.value -> "H"  (compact storage/printing)

class Suit(Enum):
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"

# creating card ranks using Enum
# - Equality: `card.rank == Rank.SEVEN`
# - Ordering/arith: use `.value` → `card.rank.value < Rank.TEN.value`
#   (Enums don’t support < > by default. If you want direct numeric comparison without `.value`,
#   switch to IntEnum — see note below.)
# - From symbols: map text tokens to members, e.g. "5"→Rank.FIVE, "A"→Rank.A, "J"→Rank.J.
# - To symbols: use `.name` for labels ("FIVE","J","A") or a custom map ("5","J","A").
# - Iteration: `for r in Rank:` yields all ranks from TWO → A.
# - JSON/printing: prefer `.name`/`.value` (don’t serialize the Enum object itself).
#
class Rank(Enum):
    TWO = 2; THREE = 3; FOUR = 4; FIVE = 5; SIX = 6; SEVEN = 7
    EIGHT = 8; NINE = 9; TEN = 10; J = 11; Q = 12; K = 13; A = 14

# # EFFECTIVE RANK — collapse 8 & 9 for burn logic
# What: Treat 8 and 9 as the *same* rank when checking sets/burns.
# How: Map both to Rank.EIGHT; all other ranks pass through unchanged.
# Use: Apply before comparing/grouping ranks for burns.

def effective_rank(rank):
    if rank in (Rank.EIGHT, Rank.NINE):
        return Rank.EIGHT
    return rank

# Card type categories
# What:
# - Buckets each card into a category the engine cares about.
# - Values are auto-assigned (1..n) with `auto()`; you compare by the *member*, not the int.
#
# Members (game-specific meaning):
# - NORMAL: standard suit+rank cards.
# - JOKER: normal joker (strength pools, special offense/defense rules).
# - PFJ: “pile-fuckery joker” (joker with extra pile-steal cost to block).
# - FRE: free action token that grants an emergency-red slot+card.
# - EMERGENCY_RED / EMERGENCY_BLUE: emergency-slot cards (for UNO/suit overrides, peeks/swaps).
# WRITE LOGICA AGAINST MEMBER NOT NUMBER (CardType.JOKER)

class CardType(Enum):
    NORMAL = auto()  
    JOKER = auto() 
    PFJ = auto() 
    FRE = auto() 
    EMERGENCY_RED = auto() 
    EMERGENCY_BLUE = auto() 

# Card class, constructs a signle card with rank, suit, type and aquired status
# rank: usually a Rank enum (e.g., Rank.FIVE). None for things like jokers.
# suit: usually a Suit enum (e.g., Suit.HEARTS). None for non-suit cards.
# card_type: a CardType (NORMAL/JOKER/PFJ/FRE/EMERGENCY_*). Defaults to NORMAL.

# __repr__ — canonical/debug string for Card
# Purpose:
#   - Returns a short, unambiguous string used by repr(card), in logs, REPL, and when
#     printing containers (e.g., lists of cards).
#
# Output rules:
#   - Special types:
#       JOKER           → "JK"
#       PFJ             → "PFJ"
#       FRE             → "FRE"
#       EMERGENCY_RED   → "RED"
#       EMERGENCY_BLUE  → "BLUE"
#   - Normal cards: "<rank><suit>" where rank ∈ {"2".."10","J","Q","K","A"} and
#     suit ∈ {"S","H","D","C"} (e.g., "10H", "QS").
#
# Implementation notes:
#   - Uses a small map so faces print as A/J/Q/K; numeric ranks use r.value (2..10).
#   - Assumes NORMAL cards always have both rank and suit (validate elsewhere).
#   - Enum comparisons: `is` or `==` both work; `is` is idiomatic for Enum members.
#   - If you want print(card) to match repr(card), add:  __str__ = __repr__

class Card:
    def __init__(self, rank=None, suit=None, card_type=CardType.NORMAL):
        self.rank = rank
        self.suit = suit
        self.type = card_type
        self.just_acquired = False  # for emergency restrictions
        
         # Validation: what combos are allowed

        if self.type is CardType.NORMAL:
            if self.rank is None or self.suit is None:
                raise ValueError("NORMAL cards require rank and suit.")
        elif self.type in (CardType.EMERGENCY_RED, CardType.EMERGENCY_BLUE):
            if self.rank is None or self.suit is None:
                raise ValueError("EMERGENCY cards require rank and suit.")
        else:  # JOKER, PFJ, FRE have no rank/suit
            if self.rank is not None or self.suit is not None:
                raise ValueError("JOKER/PFJ/FRE must not have rank or suit.")


    def __repr__(self):
        # Special tokens
        if self.type is CardType.JOKER:
            return "JK"
        if self.type is CardType.PFJ:
            return "PFJ"
        if self.type is CardType.FRE:
            return "FRE"

        # Emergency cards: include color + rank/suit when available
        if self.type in (CardType.EMERGENCY_RED, CardType.EMERGENCY_BLUE):
            color = "RED" if self.type is CardType.EMERGENCY_RED else "BLUE"
            if self.rank is not None and self.suit is not None:
                rank_map = {Rank.A: "A", Rank.K: "K", Rank.Q: "Q", Rank.J: "J"}
                rank_str = rank_map.get(self.rank, str(self.rank.value))
                return f"{color}-{rank_str}{self.suit.value}"
            return color  # fallback if no rank/suit stored

        # Normal cards
        rank_map = {Rank.A: "A", Rank.K: "K", Rank.Q: "Q", Rank.J: "J"}
        # (Assert helps catch accidental None for NORMAL cards)
        assert self.rank is not None and self.suit is not None, "NORMAL cards need rank and suit"
        rank_str = rank_map.get(self.rank, str(self.rank.value))
        return f"{rank_str}{self.suit.value}"
    
    def is_normal(self): #Checks whether this card is a standard suit+rank card 
        return self.type == CardType.NORMAL
    
    def is_ranked(self) -> bool:
        # Any card that has a rank/suit and is not a rankless token
        return self.rank is not None and self.type not in {CardType.JOKER, CardType.PFJ, CardType.FRE}

    def equivalent_for_burn(self, other): # Checks if two cards are equivalent for burn logic, ignores suit
        return self.is_normal() and other.is_normal() and effective_rank(self.rank) == effective_rank(other.rank)
    
    def copy(self): #Makes a shallow clone of the card, preserving rank, suit, type, and the just_acquired flag.
        c = Card(self.rank, self.suit, self.type)
        c.just_acquired = self.just_acquired
        return c

# Creating decks of cards
class Deck:
    def __init__(self):
        self.cards = deque()  # holds Card objects

    def shuffle(self):
        arr = list(self.cards)
        random.shuffle(arr)
        self.cards = deque(arr)

    def draw(self, n=1):
        # draw from the left (top)
        return [self.cards.popleft() for _ in range(min(n, len(self.cards)))]
    

def build_playing_deck() -> Deck:
    d = Deck(); d.cards.clear()                                              # fresh deck container
    for _ in range(2):                                                       # two common decks
        d.cards.extend(Card(r, s, CardType.NORMAL) for s in Suit for r in Rank)  # 52 normal cards
        d.cards.extend(Card(card_type=CardType.JOKER) for _ in range(2))     # +2 normal jokers per deck
        d.cards.extend(Card(card_type=CardType.PFJ)   for _ in range(1))     # +1 PFJ per deck
    d.shuffle(); return d                                                    # randomize order and return


def build_red_deck() -> Deck:
    d = Deck(); d.cards.clear()                                              # fresh red deck
    suits = list(Suit)                                                       # simple round-robin suit assignment
    add = lambda r, n: d.cards.extend(                                       #  defines small anonmous function : add n emergencies of rank r
        Card(r, suits[i % len(suits)], CardType.EMERGENCY_RED) for i in range(n)
    )
    for r, n in [                                                            # exact counts from your spec
        (Rank.FIVE,2), (Rank.SIX,2), (Rank.SEVEN,2),
        (Rank.EIGHT,4), (Rank.J,4), (Rank.Q,3), (Rank.K,2), (Rank.A,1),
        (Rank.TEN,1), (Rank.FOUR,1),
    ]: add(r, n)                                                             # add each batch
    d.cards.extend(Card(card_type=CardType.PFJ) for _ in range(2))         # +2 rankless PFJS
    d.cards.extend(Card(card_type=CardType.FRE)   for _ in range(2))         # +2 FRE tokens
    d.shuffle()
    d.origin_color = "RED"   
    return d                                                    # randomize order and return


def build_blue_deck() -> Deck:
    d = Deck(); d.cards.clear()                                              # fresh blue deck
    suits = list(Suit)                                                       # round-robin suit assignment
    add = lambda r, n: d.cards.extend(                                       # defines small anonmous function : add n emergencies of rank r
        Card(r, suits[i % len(suits)], CardType.EMERGENCY_BLUE) for i in range(n)
    )
    for r, n in [                                                            # exact counts from your spec
        (Rank.TWO,4), (Rank.THREE,4), (Rank.FOUR,4),
        (Rank.TEN,3), (Rank.J,1), (Rank.SIX,1),
    ]: add(r, n)                                                             # add each batch
    d.cards.extend(Card(card_type=CardType.PFJ) for _ in range(2))         # +2 rankless PFJS
    d.cards.extend(Card(card_type=CardType.FRE)   for _ in range(2))         # +2 FRE tokens
    d.shuffle()
    d.origin_color = "BLUE"                                             #can be used to inform source color, source_color=deck.origin_color
    return d                                                    # randomize order and return


def split_playing_deck_into_personal(play: Deck):
    half = len(play.cards) // 2                                              # integer half after shuffle
    p1 = [play.cards.popleft() for _ in range(half)]                          # player 1 gets the top half
    p2 = list(play.cards)                                                    # player 2 gets the remainder
    return p1, p2     


# Common pile in center
class CommonPile:
    def __init__(self):
        self.cards = []
        self.consumed = set()  # track consumed 2s/3s if needed #unsure purpose

    def add(self, cards): #ads cards to pile top is the leftmost tem in list
        # Insert the played cards at the left; reverse so last played is top-left.
        self.cards[:0] = reversed(cards)

    def clear(self):
        temp = self.cards[:]
        self.cards = []
        self.consumed.clear()
        return temp

    def top(self):  #returns SIGNLE top card or none if empty : needed for displaying pile surface/uno interactions
        return self.cards[0] if self.cards else None
    

    def top_group(self):
        if not self.cards:
            return []

        same, twos, threes = [], [], []
        anchor = None
        group = []

        # Walk from top → down (leftmost to right)
        for c in self.cards:
            # Tokens (JK/PFJ/FRE) are transparent: skip them entirely.
            if not c.is_ranked():
                continue

            # No anchor yet: collect 2/3; first non-2/3 ranked card becomes the anchor.
            if anchor is None:
                if c.rank is Rank.TWO:
                    twos.append(c); group.append(c); continue
                if c.rank is Rank.THREE:
                    threes.append(c); group.append(c); continue
                anchor = effective_rank(c.rank)
                same.append(c); group.append(c)
                continue

            # After we have an anchor:
            if c.rank is Rank.TWO:
                twos.append(c); group.append(c); continue
            if c.rank is Rank.THREE:
                threes.append(c); group.append(c); continue

            if effective_rank(c.rank) == anchor:
                same.append(c); group.append(c)
            else:
                break  # first different effective rank ends the group

        return group  # (you still have same/twos/threes if you ever want to inspect them)


    def detect_burns(self):
        """Top-segment burns only.
        - Walk from top down; tokens (JK/PFJ/FRE) and 2/3 are transparent.
        - First ranked non-2/3 sets the anchor (by effective rank: 8≡9).
        - Keep going while cards are tokens, 2/3, or match the anchor's effective rank.
        - Stop on the first ranked card with a different effective rank.
        - Burn if: >=4 of anchor, or >=4 of 2s, or >=4 of 3s (use //4 for multi-burns).
        """
        same = twos = threes = 0
        anchor = None

        for c in self.cards:  # top → down (left → right)     
            if not c.is_ranked():                    # token (JK/PFJ/FRE): transparent
                continue
            if c.rank is Rank.TWO:
                twos += 1                            # transparent & counted
                continue
            if c.rank is Rank.THREE:
                threes += 1                          # transparent & counted
                continue

            er = effective_rank(c.rank)              # merge 8 and 9
            if anchor is None:
                anchor = er                          # first real ranked anchor
                same += 1
                continue

            if er == anchor:
                same += 1                            # still in the top segment
            else:
                break                                # different rank ends the segment

        burns = {}
        if anchor is not None and same >= 4:
            burns[anchor] = same // 4
        if twos >= 4:
            burns[Rank.TWO] = twos // 4
        if threes >= 4:
            burns[Rank.THREE] = threes // 4
        return burns


    def __repr__(self):
        return f"{self.cards}"

class EmergencySlot:
    """Single emergency slot: knows if its locked, what card it holds, and
    whether that card is known to the owner."""
    def __init__(self, index: int, locked: bool = True):
        self.index = index
        self.locked = locked
        self.card = None          # Card or None
        self.known_to_owner = False
        self.source_color = None  # NEW: "RED" or "BLUE" (persists even after reveal)

    def is_empty(self) -> bool:
        return self.card is None

    def set_card(self, card, known: bool):
        self.card = card
        self.known_to_owner = known


# Player state
class Player:
    def __init__(self, name):
        self.name = name

        # Play areas
        self.hand = []           # cards in hand
        self.face_up = []        # 3 visible, block the face_down beneath
        self.face_down = []      # 3 hidden

        # Emergency system (now slot-based)
        self.max_emergency_slots = 4         # max 4 slots
        # Slot 0 unlocked at start; others locked
        self.emergency_slots = [EmergencySlot(i, locked=(i > 0))
                                for i in range(self.max_emergency_slots)]

        # Draw source for replenishment
        self.personal_pile = []

        # Status/means flags
        self.status_token = None              # Rank or None
        self.has_status_ability = False       # 5-card max if True
        self.can_replenish_full = False       # means-chain helper (used by game loop)

        # Per-burn allowances: { id(card): {'peek': bool, 'swap': bool} }
        self.emergency_actions = {}

    # ---- Hand size helpers -------------------------------------------------
    def hand_limit(self):
        return 5 if self.has_status_ability else 4

    def needs_replenish(self):
        return len(self.hand) < self.hand_limit()

    def pickup_common(self, cards):
        """Picking up the COMMON pile adds those cards to hand."""
        self.hand.extend(cards)

    def replenish(self):
        """Top up hand from personal pile (FIFO) until reaching limit."""
        while self.needs_replenish() and self.personal_pile:
            self.hand.append(self.personal_pile.pop(0))

    # ---- Emergency slot helpers --------------------------------------------
    

    def iter_emergency_cards(self):
        """Yield all emergency cards the player currently has (from slots)."""
        for s in self.emergency_slots:
            if s.card:
                yield s.card

    def iter_emergency_states(self):
        """Yield dicts describing each slot/card + metadata + per-burn actions."""
        for s in self.emergency_slots:
            state = {
                "slot": s.index,
                "locked": s.locked,
                "card": s.card,                          # Card or None
                "known_to_owner": s.known_to_owner if s.card else None,
                "just_acquired": (getattr(s.card, "just_acquired", False) if s.card else None),
                "actions": (self.emergency_actions.get(id(s.card)) if s.card else None),
            }
            yield state
    
    def unlocked_slots(self):
        return [s for s in self.emergency_slots if not s.locked]

    def locked_slots(self):
        return [s for s in self.emergency_slots if s.locked]

    def first_empty_unlocked_slot(self):
        for s in self.emergency_slots:
            if (not s.locked) and s.is_empty():
                return s
        return None

    def open_next_slot(self) -> bool:
        """Unlock the next locked slot (buy/FRE). Returns True if one was unlocked."""
        for s in self.emergency_slots:
            if s.locked:
                s.locked = False
                return True
        return False

    def open_next_slot_and_get(self): # FRE LOGIC RELATED
        """Unlock the next locked slot and return it (or None if none left)."""
        for s in self.emergency_slots:
            if s.locked:
                s.locked = False
                return s
        return None

    def grant_fre(self, red_deck): ### FRE LOGIC 
        """
        FRE effect:
        1) Always unlock a NEW emergency slot if one exists.
        2) Draw exactly ONE card from the RED deck (no skipping/iteration), and
            immediately place it into that slot.
        Returns the slot used, or None if no slot available or deck empty.
        """
        # 1) Always try to open a NEW slot first
        new_slot = self.open_next_slot_and_get()

        # Fall back to first empty unlocked if all slots were already open
        slot = new_slot or self.first_empty_unlocked_slot()
        if not slot:
            return None

        # 2) Draw exactly one card (no iteration over PFJ/FRE)
        drawn = red_deck.draw(1)
        if not drawn:
            return None
        card = drawn[0]

        # 3) Install it: revealed to owner, gated this burn, provenance=RED
        self.fill_slot(slot, card, known_to_owner=True, just_acquired=True, source_color="RED")
        return slot



    def start_new_burn_cycle(self):
        """Begin a fresh burn window:
        - previously acquired emergencies become eligible (clear just_acquired)
        - rebuild per-burn actions to 1-per-card (peek OR swap)
        """
        for s in self.emergency_slots:
            if s.card and hasattr(s.card, "just_acquired"):
                s.card.just_acquired = False
        self.reset_emergency_actions()

    def fill_slot(self, slot: EmergencySlot, card, known_to_owner: bool,
                just_acquired: bool = True, source_color: str | None = None):
        """
        Place a card into a specific emergency slot, record its origin color,
        and set per-burn allowances (peek/swap) correctly.

        - known_to_owner: whether the owner sees the actual card now
        - just_acquired:  if True, actions are gated this burn
        - source_color:   "RED"/"BLUE" (needed for tokens like PFJ/JOKER/FRE)
        """
        # Write the card + visibility
        slot.set_card(card, known_to_owner)

        # Persist origin color:
        # - If explicitly provided (best for tokens), use it.
        # - Else infer from EMERGENCY_* enums (tokens don't encode color).
        if source_color is not None:
            slot.source_color = source_color
        else:
            if card.type is CardType.EMERGENCY_RED:
                slot.source_color = "RED"
            elif card.type is CardType.EMERGENCY_BLUE:
                slot.source_color = "BLUE"
            # PFJ/JOKER/FRE: leave existing slot.source_color as-is if not provided

        # Gating this burn
        card.just_acquired = just_acquired
        self.emergency_actions[id(card)] = {'peek': not just_acquired, 'swap': not just_acquired}


    def emergency_cards(self):
        """Iterate current emergency cards (in any slots)."""
        for s in self.emergency_slots:
            if s.card:
                yield s.card

    def reset_emergency_actions(self):
        """Called after each burn: existing cards get one (peek OR swap) this burn.
        Newly acquired cards this burn remain disabled until the NEXT burn."""
        self.emergency_actions.clear()
        for s in self.emergency_slots:
            if s.card:
                allow = not getattr(s.card, 'just_acquired', False)
                self.emergency_actions[id(s.card)] = {'peek': allow, 'swap': allow}

    def consume_emergency_action(self, card, which: str):
        """After performing 'peek' or 'swap' on a card this burn, disable both for that card."""
        aid = id(card)
        if aid in self.emergency_actions and self.emergency_actions[aid].get(which, False):
            self.emergency_actions[aid]['peek'] = False
            self.emergency_actions[aid]['swap'] = False


    # ---- Debug/UI ----------------------------------------------------------
    def __repr__(self):
        # Status display: if you want perfect “S/0/rank” control,
        # pass game.first_burn to a renderer; this inline version is a heuristic.
        sd = self.status_token.name if self.status_token else ("S" if not self.has_status_ability else "0")
        fd = ["??"] * len(self.face_down)

        # Slots string: 🔒 for locked, E for empty-unlocked,
        # known cards print as their repr, unknown show color only.
        slot_str = []
        for s in self.emergency_slots:
            if s.locked:
                slot_str.append("🔒")
            elif s.is_empty():
                slot_str.append("E")
            else:
                if s.known_to_owner:
                    # Known to owner:
                    # - Emergencies (EMERGENCY_RED/BLUE) already include color in repr, e.g., "RED-10H".
                    # - Tokens (PFJ/JOKER/FRE) don't encode color; prefix with slot provenance if available.
                    if s.card.type in (CardType.PFJ, CardType.JOKER, CardType.FRE) and s.source_color:
                        slot_str.append(f"{s.source_color}-{repr(s.card)}")  # e.g., "RED-PFJ"
                    else:
                        slot_str.append(repr(s.card))
                else:
                    # Unknown to owner: show origin color only (falls back to "?")
                    slot_str.append(s.source_color or "?")


        return (f"{self.name} | Hand:{self.hand} | Up:{self.face_up} | Down:{fd} "
                f"| S:{sd} | Slots:{' '.join(slot_str)} | Pile:{len(self.personal_pile)}")




"""
ON BURN EMERGENCY LOGIC 
slot = player.first_empty_unlocked_slot() or (player.open_next_slot() and player.first_empty_unlocked_slot())
if slot and want_blue:
    blue_card = blue_deck.draw(1)[0]
    player.fill_slot(slot, blue_card, known_to_owner=False, just_acquired=True)
elif slot and want_red:
    red_card = red_deck.draw(1)[0]
    player.fill_slot(slot, red_card, known_to_owner=True, just_acquired=True)
"""
""""
## SWAP LOGIC
old = slot.card
new_card = (blue_deck.draw(1)[0] if swap_for_blue else red_deck.draw(1)[0])
player.consume_emergency_action(old, 'swap')          # spend this burns allowance
player.emergency_actions.pop(id(old), None)           # remove old mapping
player.fill_slot(slot, new_card, 
                 known_to_owner=(new_card.type.name.endswith("RED")),
                 just_acquired=True)                  # new card not actionable this burn
"""
## BURN LOGIC
"""""
def resolve_burns(self, player, msgs):
    # for each detected burn…
    for _ in range(num_burns):
        # 1) begin the new burn cycle for EXISTING emergencies
        player.start_new_burn_cycle()

        # 2) award the new emergency for THIS burn (remains gated)
        new_blue = Card(card_type=CardType.EMERGENCY_BLUE)
        new_blue.just_acquired = True
        player.emergency_blue.append(new_blue)

        # 3) explicitly gate the new one this cycle
        player.emergency_actions[id(new_blue)] = {'peek': False, 'swap': False}

        # 4) now offer one action per existing emergency (the new one is gated)
        self.offer_emergency_actions(player)  # your UI/logic here
"""""






# # tests
# # Tests all suits displayed correctly ----

# print(Card(Rank.TWO, Suit.CLUBS))
# print(Card(Rank.TWO, Suit.SPADES))
# print(Card(Rank.TWO, Suit.DIAMONDS))
# print(Card(Rank.TWO, Suit.HEARTS))

# # tests all types displayed correctly ----

# print(Card(card_type=CardType.JOKER))
# print(Card(card_type=CardType.FRE))
# print(Card(Rank.A, Suit.SPADES, CardType.EMERGENCY_RED))
# print(Card(Rank.A, Suit.HEARTS, CardType.EMERGENCY_BLUE))

# # Tests if jokers can have suits/ranks ----- 

# print(Card(Rank.TWO, card_type=CardType.JOKER))
# print(Card(Rank.SEVEN, Suit.HEARTS, CardType.PFJ))
# print(Card(Rank.EIGHT, Suit.SPADES, CardType.EMERGENCY_BLUE))  # ShouldNT raise value error
# print(Card(Rank.NINE, Suit.SPADES, CardType.EMERGENCY_RED))


# # test for deck count corret
# if __name__ == "__main__":
#     d = build_playing_deck()
#     print("playing:", len(d.cards))  # 110
# print("red:", len(build_red_deck().cards))    # 26
# print("blue:", len(build_blue_deck().cards))  # 21


# # ---- build & dump decks (minimal) ----
# def print_deck(title, deck):
#     print(f"\n== {title} ==")
#     print(f"Total: {len(deck.cards)}")
#     for c in deck.cards:
#         print(repr(c))

# if __name__ == "__main__":
#     # Optional: seed for repeatable shuffles
#     # import random; random.seed(123)

#     playing = build_playing_deck()
#     red     = build_red_deck()
#     blue    = build_blue_deck()

# print_deck("Playing deck (2x52 + 4 JK + 2 PFJ)", playing)
# print_deck("Red deck", red)
# print_deck("Blue deck", blue)

# # prints in order for easy checking
# print("\n".join(repr(c) for c in sorted(playing.cards, key=lambda c: (c.type is not CardType.NORMAL, c.suit.value if c.suit else "Z", c.rank.value if c.rank else -1, repr(c)))))