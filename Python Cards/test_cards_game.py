
import unittest
import random

# Ensure we can import the engine module from /mnt/data
import sys
sys.path.append('/mnt/data')

from CardsGameEngine1 import (
    Color, Suit, Rank, CardType, Card,
    Deck, build_playing_deck, build_red_deck, build_blue_deck,
    split_playing_deck_into_personal, CommonPile, EmergencySlot, Player, effective_rank
)

class TestCardBasics(unittest.TestCase):
    def test_effective_rank(self):
        self.assertEqual(effective_rank(Rank.EIGHT), Rank.EIGHT)
        self.assertEqual(effective_rank(Rank.NINE), Rank.EIGHT)
        self.assertEqual(effective_rank(Rank.SEVEN), Rank.SEVEN)

    def test_card_repr_and_validation(self):
        # Normal card requires rank and suit
        c = Card(Rank.A, Suit.HEARTS, CardType.NORMAL)
        self.assertEqual(repr(c), "AH")
        # Joker must not have rank/suit
        with self.assertRaises(ValueError):
            Card(Rank.TWO, Suit.SPADES, CardType.JOKER)
        with self.assertRaises(ValueError):
            Card(suit=Suit.SPADES, card_type=CardType.JOKER)
        # Emergency cards need rank/suit
        c_red = Card(Rank.K, Suit.CLUBS, CardType.EMERGENCY_RED)
        self.assertTrue("RED" in repr(c_red))
        c_blue = Card(Rank.TEN, Suit.SPADES, CardType.EMERGENCY_BLUE)
        self.assertTrue("BLUE" in repr(c_blue))

class TestDeckBuilders(unittest.TestCase):
    def test_playing_deck_counts_and_tokens(self):
        d = build_playing_deck()
        self.assertEqual(len(d.cards), 110)  # 2*52 + 4 JK + 2 PFJ = 110 total
        # Count tokens
        toks = [c for c in d.cards if c.type in (CardType.JOKER, CardType.PFJ)]
        self.assertEqual(len(toks), 6)
        normals = [c for c in d.cards if c.type == CardType.NORMAL]
        self.assertEqual(len(normals), 104)

    def test_red_blue_decks_counts(self):
        red = build_red_deck()
        blue = build_blue_deck()
        self.assertEqual(len(red.cards), 26)
        self.assertEqual(len(blue.cards), 21)

    def test_split_playing_deck(self):
        d = build_playing_deck()
        p1, p2 = split_playing_deck_into_personal(d)
        self.assertEqual(len(p1) + len(p2), 110)
        # They should be roughly half (off by 1 if odd)
        self.assertTrue(abs(len(p1) - len(p2)) <= 1)

class TestCommonPileCore(unittest.TestCase):
    def setUp(self):
        self.pile = CommonPile()

    def card(self, r, s):
        return Card(r, s, CardType.NORMAL)

    def test_add_and_top_order(self):
        # Add a single card; top should be that card
        c1 = self.card(Rank.FIVE, Suit.HEARTS)
        self.pile.add([c1])
        self.assertEqual(self.pile.top(), c1)

        # Add another single card; top should be the newly added
        c2 = self.card(Rank.SEVEN, Suit.SPADES)
        self.pile.add([c2])
        self.assertEqual(self.pile.top(), c2)

        # Add two cards in one play; reversed insertion puts last in list on top
        c3 = self.card(Rank.NINE, Suit.CLUBS)
        c4 = self.card(Rank.NINE, Suit.DIAMONDS)
        self.pile.add([c3, c4])  # reversed → top should be c4
        self.assertEqual(self.pile.top(), c4)

    def test_clear_resets(self):
        c1 = self.card(Rank.FOUR, Suit.SPADES)
        self.pile.add([c1])
        prev = self.pile.clear()
        self.assertEqual(prev, [c1])
        self.assertEqual(len(self.pile.cards), 0)
        self.assertEqual(len(self.pile.consumed), 0)

    def test_top_group_basic(self):
        # Build: top-left is last item in .add([...]) call due to reverse
        seq = [
            self.card(Rank.EIGHT, Suit.HEARTS),
            self.card(Rank.NINE, Suit.SPADES),
            self.card(Rank.EIGHT, Suit.DIAMONDS),
        ]
        self.pile.add(seq)  # top group should include all three (8/9 ≡ 8)
        grp = self.pile.top_group()
        # In top_group implementation, tokens skipped but normal cards included
        # We're not guaranteed identity due to insertion order; check contents
        self.assertEqual(len(grp), 3)
        eff = {effective_rank(c.rank) for c in grp if c.is_normal()}
        self.assertEqual(eff, {Rank.EIGHT})

    def test_top_group_stops_on_different_rank(self):
        self.pile.add([
            self.card(Rank.EIGHT, Suit.HEARTS),
            self.card(Rank.EIGHT, Suit.SPADES),
            self.card(Rank.SEVEN, Suit.CLUBS),  # different rank breaks
            self.card(Rank.EIGHT, Suit.DIAMONDS)
        ])
        grp = self.pile.top_group()
        # Should capture only the first 8 at the top of pile
        self.assertEqual(len([c for c in grp if c.is_normal()]), 1)

    def test_detect_burns_anchor(self):
        # 4 of same effective rank (8/9) at top segment → one burn
        self.pile.add([
            self.card(Rank.NINE, Suit.HEARTS),
            self.card(Rank.EIGHT, Suit.SPADES),
            self.card(Rank.NINE, Suit.DIAMONDS),
            self.card(Rank.NINE, Suit.CLUBS),
        ])
        burns = self.pile.detect_burns()
        self.assertIn(Rank.EIGHT, burns)
        self.assertEqual(burns[Rank.EIGHT], 1)

    def test_detect_burns_twos_threes(self):
        # Tokens are transparent; mix some
        jk = Card(card_type=CardType.JOKER)
        pfj = Card(card_type=CardType.PFJ)
        # Add 4x TWOs interleaved with tokens → burn on TWO
        seq = [jk,
               self.card(Rank.TWO, Suit.SPADES),
               pfj,
               self.card(Rank.TWO, Suit.HEARTS),
               self.card(Rank.TWO, Suit.CLUBS),
               self.card(Rank.TWO, Suit.DIAMONDS)]
        self.pile.add(seq)
        burns = self.pile.detect_burns()
        self.assertIn(Rank.TWO, burns)
        self.assertEqual(burns[Rank.TWO], 1)

        # Clear and test 3s
        self.pile.clear()
        self.pile.add([
            self.card(Rank.THREE, Suit.SPADES),
            self.card(Rank.THREE, Suit.HEARTS),
            self.card(Rank.THREE, Suit.CLUBS),
            self.card(Rank.THREE, Suit.DIAMONDS),
        ])
        burns = self.pile.detect_burns()
        self.assertIn(Rank.THREE, burns)
        self.assertEqual(burns[Rank.THREE], 1)

class TestEmergencySlotsAndPlayer(unittest.TestCase):
    def test_initial_slots_and_unlock(self):
        p = Player("T")
        # slot 0 is unlocked, others locked
        self.assertFalse(p.emergency_slots[0].locked)
        self.assertTrue(all(s.locked for s in p.emergency_slots[1:]))
        # unlock next slot
        self.assertTrue(p.open_next_slot())
        self.assertFalse(p.emergency_slots[1].locked)

    def test_fill_slot_and_actions_gating(self):
        p = Player("T")
        # ensure slot0 is unlocked and empty
        slot = p.first_empty_unlocked_slot()
        red = Card(Rank.K, Suit.SPADES, CardType.EMERGENCY_RED)
        p.fill_slot(slot, red, known_to_owner=True, just_acquired=True)
        # Newly acquired: no peek/swap this burn
        self.assertFalse(p.emergency_actions[id(red)]['peek'])
        self.assertFalse(p.emergency_actions[id(red)]['swap'])
        # Next burn: reset should allow one action
        p.start_new_burn_cycle()
        self.assertTrue(p.emergency_actions[id(red)]['peek'])
        # Consume
        p.consume_emergency_action(red, 'peek')
        self.assertFalse(p.emergency_actions[id(red)]['peek'])
        self.assertFalse(p.emergency_actions[id(red)]['swap'])

    def test_replenish_from_personal(self):
        p = Player("T")
        # give hand below limit (default 4)
        p.hand = [Card(Rank.FOUR, Suit.HEARTS)]
        p.personal_pile = [Card(Rank.FIVE, Suit.SPADES), Card(Rank.SIX, Suit.SPADES)]
        p.replenish()
        self.assertEqual(len(p.hand), 3)  # 1 + 2 drawn

if __name__ == "__main__":
    unittest.main(verbosity=2)
