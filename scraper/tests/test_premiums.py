"""Brand premium parser against saved PBS pages (fixtures/, fetched 17 Oct 2026).

Run from the repo root:  python3 -m unittest discover -s scraper/tests -v
The schedule is split by the brand's first letter; the bare URL shows only "A".
Before 17 Oct 2026 the scraper read that page alone, so Spiractin, Provera, Doryx
and Mayne Pharma Doxycycline never reached the costs page (fact check row P39).
"""
import pathlib, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import premiums  # noqa: E402

FIX = HERE / "fixtures"
WORDS = ["spironolactone", "cyproterone acetate", "medroxyprogesterone acetate", "doxycycline",
         "levonorgestrel", "estradiol", "testosterone"]
EMPTY = "<html><body><p>No records found. Try another initial instead.</p></body></html>"


def fake_get(url):
    name = "pbs-brand-premium" + ("-" + url.split("initial=")[1] if "initial=" in url else "") + ".html"
    f = FIX / name
    return f.read_text() if f.exists() else EMPTY


class PremiumRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        premiums.time.sleep = lambda s: None
        cls.rows = premiums.premium_rows(WORDS, get=fake_get)
        cls.by = {}
        for r in cls.rows:
            cls.by.setdefault(r["brand"], []).append(r)

    def test_reads_every_letter(self):
        for brand in ("Aldactone", "Androcur", "Spiractin 25", "Spiractin 100", "Provera", "Doryx", "Mayne Pharma Doxycycline"):
            self.assertIn(brand, self.by, brand + " missing: only the A page was read?")

    def test_known_premiums(self):
        sp = {r["packs"]: r["premium"] for r in self.by["Spiractin 25"]}
        self.assertEqual(sp, {"1": "4.42", "2": "8.84"})
        self.assertIn("4.74", [r["premium"] for r in self.by["Doryx"]])
        self.assertIn("2.41", [r["premium"] for r in self.by["Mayne Pharma Doxycycline"]])

    def test_excludes_rows_the_site_does_not_cover(self):
        self.assertNotIn("Levlen ED", self.by)                     # combined pill, matched only on levonorgestrel
        self.assertFalse([r for r in self.rows if "doxycycline 100 mg" in r["product"]])
        self.assertNotIn("Advantan", self.by)                      # unrelated medicine on the same page

    def test_no_duplicates_from_default_and_a(self):
        self.assertEqual(len(self.by["Aldactone"]), len({(r["product"], r["packs"]) for r in self.by["Aldactone"]}))

    def test_letters_come_from_the_page(self):
        ls = premiums.letters((FIX / "pbs-brand-premium.html").read_text())
        self.assertIn("s", ls); self.assertIn("q", ls); self.assertNotIn("x", ls)

    def test_layout_change_fails_loudly(self):
        bad = lambda url: "<html><body><p>Maintenance</p></body></html>" if "initial=s" in url else fake_get(url)
        with self.assertRaises(SystemExit):
            premiums.premium_rows(WORDS, get=bad)


if __name__ == "__main__":
    unittest.main()
