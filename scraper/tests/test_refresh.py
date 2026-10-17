"""TGA shortage parser against saved TGA pages (fixtures/, fetched 17 Oct 2026).

Run from the repo root:  python3 -m unittest discover -s scraper/tests -v
The TGA table now has "Product details", "Supply Impact Dates" ("From 17 Jan 2024 to
31 Dec 2026") and "Further Details" columns. Before 17 Oct 2026 the scraper looked for
"expected resolution date", so no return date reached the site (fact check row P21).
"""
import pathlib, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import refresh  # noqa: E402

FIX = HERE / "fixtures"


def rows(ingredient):
    return refresh.parse_rows((FIX / f"tga-{ingredient}.html").read_text(), ingredient, "x", "https://example")


class TgaRows(unittest.TestCase):
    def test_estradot_return_date(self):
        r = {x["brand"].split()[1]: x for x in rows("estradiol")}
        self.assertEqual(set(r), {"25", "50", "75", "100"})
        self.assertEqual(r["100"]["status"], "limited")
        self.assertEqual(r["100"]["expectedReturn"], "31 Dec 2026")
        self.assertEqual(r["25"]["since"], "04 Aug 2023")
        self.assertTrue(r["50"]["brand"].startswith("ESTRADOT 50 estradiol"))
        self.assertNotIn("AUST R", r["50"]["brand"])

    def test_resolved_is_available_without_dates(self):
        (p,) = rows("estradiol-valerate")
        self.assertEqual((p["status"], p["since"], p["expectedReturn"]), ("in_supply", "—", "—"))

    def test_anticipated_stays_available_with_dates(self):
        prov = [x for x in rows("medroxyprogesterone-acetate") if x["brand"].startswith("PROVERA")][0]
        self.assertEqual(prov["status"], "in_supply")
        self.assertIn("expected from 07 Dec 2026", prov["statusLabel"])
        self.assertEqual(prov["expectedReturn"], "15 Feb 2027")

    def test_deletion_from_market_resolved(self):
        (z,) = rows("goserelin")
        self.assertEqual(z["status"], "in_supply")

    def test_pin_until(self):
        e = {"pin": True, "pinUntil": "2026-10-30"}
        self.assertTrue(refresh.pinned(e, "2026-10-30"))
        self.assertFalse(refresh.pinned(e, "2026-10-31"))
        self.assertTrue(refresh.pinned({"pin": True}, "2030-01-01"))
        self.assertFalse(refresh.pinned({}, "2026-10-01"))

    def test_delisting_follows_pin_until(self):
        # Zoladex (data/manual.json): pinned to 31 Oct 2026; the daily run resumes TGA data from 1 Nov 2026
        z = {"id": "zoladex", "status": "delisting", "pin": True, "pinUntil": "2026-10-31"}
        self.assertTrue(refresh.keeps_own_status(z, "2026-10-31"))
        self.assertFalse(refresh.keeps_own_status(z, "2026-11-01"))
        self.assertTrue(refresh.keeps_own_status({"status": "delisting"}, "2030-01-01"))   # no date: kept until edited
        self.assertFalse(refresh.keeps_own_status({"status": "in_supply"}, "2026-10-01"))

    def test_manual_remove_drops_row(self):
        # Duphaston (data/manual.json, 17 Oct 2026): not on the ARTG, so "remove": true takes it off /supply at the next refresh
        manual = [{"id": "duphaston", "remove": True}, {"id": "androcur", "brand": "Androcur"}]
        rows_ = [{"id": "duphaston", "ingredient": "dydrogesterone"}, {"id": "androcur"}]
        self.assertEqual(refresh.removed_ids(manual), {"duphaston"})
        self.assertEqual([r["id"] for r in refresh.drop_removed(rows_, manual)], ["androcur"])
        self.assertEqual([r["id"] for r in refresh.drop_removed(manual, manual)], ["androcur"])


if __name__ == "__main__":
    unittest.main()
