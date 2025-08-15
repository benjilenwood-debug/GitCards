# game_complete.py
# Final complete interactive text-based card game per document and conversation
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

# Card suits and ranks
enum_map = {}
class Suit(Enum):
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"

enum_map['S'] = Suit.SPADES
enum_map['H'] = Suit.HEARTS
enum_map['D'] = Suit.DIAMONDS
enum_map['C'] = Suit.CLUBS

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

enum_map.update({str(r.value): r for r in Rank if r.value <= 10})
enum_map['J'] = Rank.J
enum_map['Q'] = Rank.Q
enum_map['K'] = Rank.K
enum_map['A'] = Rank.A

# Map for burn equivalence

def effective_rank(r):
    return Rank.EIGHT if r in (Rank.EIGHT, Rank.NINE) else r

# Card types
class CardType(Enum):
    NORMAL = auto()
    JOKER = auto()
    PFJ = auto()
    FRE = auto()
    EMERGENCY_RED = auto()
    EMERGENCY_BLUE = auto()

# Card class
class Card:
    def __init__(self, rank=None, suit=None, card_type=CardType.NORMAL):
        self.rank = rank
        self.suit = suit
        self.type = card_type
        self.just_acquired = False  # for emergency actions
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
        m = {Rank.A: "A", Rank.J: "J", Rank.Q: "Q", Rank.K: "K"}
        rv = m.get(self.rank, str(self.rank.value))
        return f"{rv}{self.suit.value}"
    def is_normal(self):
        return self.type == CardType.NORMAL
    def equivalent_for_burn(self, other):
        return self.is_normal() and other.is_normal() and effective_rank(self.rank) == effective_rank(other.rank)
    def copy(self):
        c = Card(self.rank, self.suit, self.type)
        c.just_acquired = self.just_acquired
        return c

# Deck and piles
class Deck:
    def __init__(self):
        self.cards = deque()
        self.build()
        self.shuffle()
    def build(self):
        self.cards.clear()
        for s in Suit:
            for r in Rank:
                if r.value >= 2:
                    self.cards.append(Card(r, s))
    def shuffle(self):
        arr = list(self.cards)
        random.shuffle(arr)
        self.cards = deque(arr)
    def draw(self, n=1):
        res = []
        for _ in range(n):
            if self.cards:
                res.append(self.cards.popleft())
        return res

class CommonPile:
    def __init__(self):
        self.cards = []
        self.consumed = set()
    def add(self, cs):
        self.cards.extend(cs)
    def clear(self):
        tmp = self.cards[:]
        self.cards = []
        self.consumed.clear()
        return tmp
    def top(self):
        return self.cards[-1] if self.cards else None
    def detect_burns(self):
        cnt = Counter()
        for c in self.cards:
            if c.is_normal() and c.rank not in (Rank.TWO, Rank.THREE):
                cnt[effective_rank(c.rank)] += 1
        return {r: cnt[r]//4 for r in cnt if cnt[r] >= 4}
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
        self.emergency_actions = {}
    def hand_limit(self): return 5 if self.has_status_ability else 4
    def needs_replenish(self):
        return len(self.hand) < (self.hand_limit() if self.has_status_ability else 4)
    def pickup_common(self, cs):
        self.hand.extend(cs)
        self.personal_pile = []
    def replenish(self):
        while self.needs_replenish() and self.personal_pile:
            self.hand.append(self.personal_pile.pop(0))
    def reset_emergency_actions(self):
        self.emergency_actions = {}
        for c in self.emergency_red + self.emergency_blue:
            self.emergency_actions[id(c)] = {'peek':True,'swap':True}
    def __repr__(self):
        sd = self.status_token.name if self.status_token else ("S" if not self.has_status_ability else "0")
        fd = ["??"]*len(self.face_down)
        return f"{self.name}|_hand:{self.hand}_up:{self.face_up}_down:{fd}_S:{sd}_R:{self.emergency_red}_B:{self.emergency_blue}_P:{len(self.personal_pile)}"

# Game engine
class GameState:
    def __init__(self, players, interactive=True):
        self.common_pile = CommonPile()
        self.players = players
        self.current_idx = 0
        self.first_burn = False
        self.status_rank = None
        self.offenses = []
        self.interactive = interactive
    def current(self): return self.players[self.current_idx]
    def opponent(self): return self.players[1-self.current_idx]
    def advance(self): self.current_idx = 1-self.current_idx
    def set_status(self,p,r):
        if not self.first_burn:
            self.first_burn=True;self.status_rank=r;p.status_token=r;p.has_status_ability=True
    def transfer_status(self,src,tgt):
        if tgt.has_status_ability:
            tgt.has_status_ability=False;tgt.status_token=None;src.has_status_ability=True;src.status_token=self.status_rank
    def resolve_burns(self,p,msgs):
        b=self.common_pile.detect_burns()
        if not b: return
        rs=list(b.keys());order=rs
        if self.interactive and len(rs)>1:
            print("Burns:",rs)
            ch=input(f"{p.name} order? ").split(',')
            cm=[x.strip().upper() for x in ch]
            order=[r for r in rs if r.name in cm] or rs
        for r in order:
            for i in range(b[r]):
                self.set_status(p,r)
                msgs.append(f"Burn {r.name}{i+1}")
                self.common_pile.clear()
                nb=Card(card_type=CardType.EMERGENCY_BLUE);nb.just_acquired=True;p.emergency_blue.append(nb)
                msgs.append("blue emergency")
                p.reset_emergency_actions();p.emergency_actions[id(nb)]={'peek':False,'swap':False}
                self.emergency_prompt(p,msgs)
    def emergency_prompt(self,p,msgs):
        for c in p.emergency_red+p.emergency_blue:
            aid=id(c);av=p.emergency_actions.get(aid,{});
            if c.just_acquired: continue
            if av.get('peek') and self.interactive:
                if input(f"{p.name} peek {c}? (y/n)").lower()=='y': msgs.append(f"peek {c}");p.emergency_actions[aid]['peek']=False
            if av.get('swap') and self.interactive:
                if input(f"{p.name} swap {c}? (y/n)").lower()=='y':new=Card(card_type=c.type);new.just_acquired=True;idx=p.emergency_red.index(c) if c.type==CardType.EMERGENCY_RED else p.emergency_blue.index(c);(p.emergency_red if c.type==CardType.EMERGENCY_RED else p.emergency_blue)[idx]=new;msgs.append(f"swap {c}");p.emergency_actions[aid]['swap']=False
    def play(self,pl,cs,pair=False):
        msgs=[];win=False;opp=self.opponent()
        for c in cs:
            if c in pl.hand: pl.hand.remove(c)
        for c in cs:
            if c.type==CardType.FRE: nr=Card(card_type=CardType.EMERGENCY_RED);nr.just_acquired=True;pl.emergency_red.append(nr);msgs.append("FRE red");pl.reset_emergency_actions();pl.emergency_actions[id(nr)]={'peek':False,'swap':False}
        m5=any(c.is_normal()and c.rank in (Rank.FIVE,Rank.SEVEN) for c in cs)
        if m5 and opp.has_status_ability: self.transfer_status(pl,opp);msgs.append("status tr")
        if m5:pl.can_replenish_full=opp.can_replenish_full=True
        if pair:pl.can_replenish_full=False
        self.common_pile.add(cs);msgs.append(f"play{cs}")
        if len(cs)==1 and cs[0].is_normal() and cs[0].rank==Rank.TEN: self.common_pile.clear();msgs.append("TEN wipe")
        for c in cs:
            if c.type==CardType.PFJ:
                if opp.personal_pile: pl.personal_pile+=opp.personal_pile;opp.personal_pile.clear();msgs.append("PFJ steal")
                else:msgs.append("PFJ1")
        jks=[c for c in cs if c.type==CardType.JOKER]
        if jks: self.offenses.append({'att':pl,'str':len(jks),'res':False});msgs.append(f"JK off{len(jks)}")
        self.resolve_burns(pl,msgs)
        if not(pl.hand or pl.face_up or pl.face_down or pl.personal_pile): msgs.append(f"{pl.name} wins");win=True
        return msgs,win
    def resolve_offenses(self):
        msgs=[]
        for a in list(self.offenses):
            if a['res']:continue
            pl=a['att'];df=self.opponent();req=a['str'];prov=0;used=[]
            for c in list(df.hand):
                if prov>=req:break
                if c.type==CardType.JOKER or (c.is_normal()and c.rank==Rank.FOUR) or c.type==CardType.PFJ:prov+=1;used.append(c)
            if prov>=req:
                need=req;cons=[]
                for c in used:
                    if need<=0:break
                    if c in df.hand:df.hand.remove(c);cons.append(c);need-=1
                msgs.append(f"blocked{cons}")
            else:
                msgs.append("block fail");df.pickup_common(self.common_pile.clear());msgs.append("pickup forced")
            a['res']=True
        self.offenses=[a for a in self.offenses if not a['res']]
        return msgs
    def __repr__(self):return f"Pile:{self.common_pile}\n{self.players[0]}\n{self.players[1]}"

def parse_card(t):
    T=t.upper()
    if T=="JK":return Card(card_type=CardType.JOKER)
    if T=="PFJ":return Card(card_type=CardType.PFJ)
    if T=="FRE":return Card(card_type=CardType.FRE)
    rp,sc=T[:-1],T[-1]
    s=Suit(sc)
    r=enum_map.get(rp)
    return Card(r,s)

def process_command(g,cmd):
    tk=shlex.split(cmd)
    if not tk:return["Empty"],False
    pl=g.current();pm=tk[0].lower();ms=[];w=False
    if pm=="play":
        cs=[];pair=False
        for t in tk[1:]:
            if "+" in t:
                ps=[parse_card(x) for x in t.split("+")];cs+=ps;su=[c.suit for c in ps if c.is_normal()];rk=[c.rank for c in ps if c.is_normal()]
                if any(r==Rank.THREE for r in rk)and len(set(su))==1:pair=True
            else:cs.append(parse_card(t))
        for c in cs:
            if c not in pl.hand:return[f"no{c}"],False
        ms,w=g.play(pl,cs,pair)
        ms+=g.resolve_offenses()
        if not w:g.advance()
        return ms,w
    if pm.startswith("burn"):
        try:
            p=cmd.split(",",1)[1];rp,cp=p.split("x");cp=int(cp);rp=rp.strip().upper();r=Rank[int(rp) if rp.isdigit() else rp]
        except:return["err"],False
        cs=[Card(r,random.choice(list(Suit))) for _ in range(cp)]
        ms,w=g.play(pl,cs);ms+=g.resolve_offenses();
        if not w:g.advance()
        return ms,w
    if pm=="pickup":
        if not g.common_pile.cards:return["none"],False
        pl.pickup_common(g.common_pile.clear());return["picked"],False
    return["unk"],False


'''
with open('/mnt/data/game_complete.py','w') as f:
    f.write(game_complete_code)
