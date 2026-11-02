import random
import time
import unittest

from aid_register import core, create_app
from aid_register.core import Household, clean_phone, entitlement, find_duplicates, jaro, jaro_winkler, name_score, normalise, pair_score, round_totals


class TestStrings(unittest.TestCase):
    def test_published_jaro_values(self):
        self.assertAlmostEqual(jaro("MARTHA", "MARHTA"), 0.944, places=3)
        self.assertAlmostEqual(jaro("DIXON", "DICKSONX"), 0.767, places=3)
        self.assertAlmostEqual(jaro("JELLYFISH", "SMELLYFISH"), 0.896, places=3)

    def test_published_jaro_winkler_values(self):
        self.assertAlmostEqual(jaro_winkler("MARTHA", "MARHTA"), 0.961, places=3)
        self.assertAlmostEqual(jaro_winkler("DWAYNE", "DUANE"), 0.84, places=2)
        self.assertAlmostEqual(jaro_winkler("DIXON", "DICKSONX"), 0.813, places=3)

    def test_edges(self):
        self.assertEqual(jaro("", "abc"), 0)
        self.assertEqual(jaro("abc", "abc"), 1)
        self.assertEqual(jaro("abc", "xyz"), 0)

    def test_normalise_removes_titles_and_evens_spelling(self):
        self.assertEqual(normalise("Md. Rahim"), normalise("Mohammad Raheem"))
        self.assertEqual(normalise("Khadija"), normalise("Kadija"))

    def test_word_order_does_not_matter(self):
        self.assertAlmostEqual(name_score("Rahima Begum", "Begum Rahima"), 1)

    def test_common_spellings_meet(self):
        for a, b in [("Rahima Khatun", "Rohima Khatoon"), ("Shafiqul Islam", "Safikul Islam"), ("Abdul Karim", "Abdul Kareem"), ("Mohammad Yusuf", "Md Yousuf")]:
            self.assertGreater(name_score(a, b), 0.85, (a, b))

    def test_different_people_stay_apart(self):
        for a, b in [("Rahima Begum", "Fatema Khatun"), ("Abdul Karim", "Nur Islam"), ("Hasina", "Shahana Parvin")]:
            self.assertLess(name_score(a, b), 0.8, (a, b))

    def test_bangla_names(self):
        self.assertEqual(name_score("রহিমা বেগম", "রহিমা বেগম"), 1)

    def test_empty(self):
        self.assertEqual(name_score("", "x"), 0)

    def test_phone(self):
        self.assertEqual(clean_phone("+880 1712-345678"), clean_phone("01712345678"))


class TestDuplicates(unittest.TestCase):
    def test_finds_a_respelled_record(self):
        r = [Household(1, "Rahima Khatun", 5, "01712345678"), Household(2, "Rohima Khatoon", 5, "+8801712345678"), Household(3, "Nur Jahan", 3)]
        pairs = find_duplicates(r)
        self.assertEqual([(p[1], p[2]) for p in pairs], [(1, 2)])
        self.assertIn("same phone", pairs[0][3])

    def test_same_name_different_father_is_not_flagged(self):
        a = Household(1, "Abdul Karim", 4, father="Nur Islam", birth_year=1970)
        b = Household(2, "Abdul Karim", 6, father="Rafiq Mia", birth_year=1995)
        self.assertEqual(find_duplicates([a, b]), [])
        self.assertLess(pair_score(a, b)[0], 0.7)

    def test_blocking_matches_a_full_comparison(self):
        rng = random.Random(1)
        first = ["Rahima", "Fatema", "Karim", "Nur", "Hasan", "Sultana", "Jamal", "Rina"]
        last = ["Begum", "Khatun", "Islam", "Mia", "Uddin", "Akter"]
        people = [Household(i, f"{rng.choice(first)} {rng.choice(last)}", 3) for i in range(120)]
        fast = {(p[1], p[2]) for p in find_duplicates(people)}
        slow = {(a.id, b.id) for i, a in enumerate(people) for b in people[i + 1:] if pair_score(a, b)[0] >= 0.88}
        self.assertEqual(len(fast - slow), 0)
        self.assertGreaterEqual(len(fast & slow) / max(len(slow), 1), 0.95)

    def test_large_register_stays_fast(self):
        rng = random.Random(2)
        names = ["".join(rng.choice("abdefhiklmnoprstu") for _ in range(6)) for _ in range(5000)]
        people = [Household(i, n + " " + rng.choice(names), 3) for i, n in enumerate(names)]
        t = time.time()
        find_duplicates(people)
        self.assertLess(time.time() - t, 20)


class TestEntitlement(unittest.TestCase):
    R = [("Rice kg", 0, 6, 40), ("Oil l", 1, 0.25, 3), ("Soap", 2, 0, None)]

    def test_scale_and_cap(self):
        self.assertEqual(entitlement(4, self.R), {"Rice kg": 24, "Oil l": 2.0, "Soap": 2})
        self.assertEqual(entitlement(10, self.R)["Rice kg"], 40)
        self.assertEqual(entitlement(10, self.R)["Oil l"], 3)

    def test_needs_a_person(self):
        with self.assertRaises(ValueError):
            entitlement(0, self.R)

    def test_totals(self):
        self.assertEqual(round_totals([Household(1, "a", 2), Household(2, "b", 3)], self.R)["Rice kg"], 30)


class TestApp(unittest.TestCase):
    def setUp(self):
        self.a = create_app(":memory:")
        self.a.post("/households", head="Rahima Khatun", members=4, phone="01712345678")
        self.a.post("/households", head="Karim Mia", members=2)
        self.a.post("/rounds", name="November", ration="Rice kg, 0, 6, 40\nOil l, 1, 0.25, 3")

    def text(self, url):
        return self.a.get(url).body.decode()

    def test_collection_shows_what_to_give(self):
        r = self.a.post("/round/1", household=1, staff="S")
        self.assertEqual(r.status, 303)
        self.assertIn("give 24 Rice kg, 2 Oil l", self.text(r.headers["Location"]))
        self.assertIn("1 of 2", self.text("/round/1"))

    def test_second_collection_is_blocked(self):
        self.a.post("/round/1", household=1)
        r = self.a.post("/round/1", household=1)
        self.assertEqual(r.status, 409)
        self.assertIn("already collected", r.body.decode())
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM collections"), 1)

    def test_unknown_household(self):
        self.assertEqual(self.a.post("/round/1", household=99).status, 404)

    def test_missing_list(self):
        self.a.post("/round/1", household=1)
        csv = self.a.get("/round/1/missing.csv").body.decode()
        self.assertIn("Karim Mia", csv)
        self.assertNotIn("Rahima", csv)

    def test_review_keeps_people_until_a_person_decides(self):
        self.a.post("/households", head="Rohima Khatoon", members=4, phone="+8801712345678")
        self.assertIn("Rohima", self.text("/duplicates"))
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM households WHERE status = 'active'"), 3)
        self.a.post("/duplicates", a=1, b=3, verdict="different")
        self.assertIn("No possible duplicates", self.text("/duplicates"))
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM households WHERE status = 'active'"), 3)

    def test_confirmed_merge_stops_collection(self):
        self.a.post("/households", head="Rohima Khatoon", members=4, phone="+8801712345678")
        self.a.post("/duplicates", a=1, b=3, verdict="same")
        self.assertEqual(self.a.post("/round/1", household=3).status, 404)

    def test_search(self):
        self.assertIn("Karim", self.text("/households?q=karim"))
        self.assertNotIn("Rahima", self.text("/households?q=karim"))

    def test_bad_inputs(self):
        self.assertEqual(self.a.post("/households", head="x", members=0).status, 400)
        self.assertEqual(self.a.post("/rounds", name="y", ration="Rice").status, 400)
        self.assertEqual(self.a.post("/rounds", name="November", ration="Rice, 1, 1").status, 409)


if __name__ == "__main__":
    unittest.main()
