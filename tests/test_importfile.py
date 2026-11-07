import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import importfile  # noqa: E402

M = "year2-cns"
LECTURES = [{"lecture_id": f"{M}:L01", "title": "Pain control", "subject": "Physiology", "pdf_pages": [2, 9]},
            {"lecture_id": f"{M}:L02", "title": "Brain tumours", "subject": "Pathology", "pdf_pages": [9, 20]}]


def q(wk, key=0, conflict=False, chat="Batch58ATM", options=("a", "b")):
    return {"word_key": wk, "question": f"stem {wk}", "options": list(options), "key": key, "key_conflict": conflict,
            "solution": None, "votes": [7, 3], "total": 10, "importance_score": 2, "repetition_count": 2,
            "source_url": "https://t.me/x/1",
            "sightings": [{"chat": chat, "msg_id": 1, "date": "2026-11-05T10:00:00", "header": "h", "doctor": None,
                           "link": "https://t.me/x/1"}]}


def lab(wk, lecture=f"{M}:L01", module=M, doctors=("Omar Qasem",), kinds=("doctor",)):
    return {"word_key": wk, "module": module, "lecture_id": lecture, "doctors": list(doctors), "kinds": list(kinds)}


class TestImportFile(unittest.TestCase):
    def test_only_keyed_lecture_rows_of_site_subjects_go_in(self):
        bank = [q("ok"), q("nokey", key=None), q("clash", conflict=True), q("six", options="abcdef"),
                q("nolec"), q("patho"), q("other"), q("y1", chat="ZAG_59_Polls")]
        labels = [lab("ok"), lab("nokey"), lab("clash"), lab("six"), lab("nolec", lecture=None),
                  lab("patho", lecture=f"{M}:L02"), lab("other", module="year1-musculoskeletal"), lab("y1")]
        data, skipped = importfile.build(M, bank, labels, LECTURES, {"Omar Qasem": "dr-omar-qassem-phys"},
                                         {"Batch58ATM": 58, "ZAG_59_Polls": 59})
        self.assertEqual(dict(skipped), {"no_key": 1, "key_conflict": 1, "options_count": 1, "no_lecture": 1,
                                         "subject_not_on_site": 1})
        self.assertEqual([x["stem"] for x in data["questions"]], ["stem ok", "stem y1"])
        first = data["questions"][0]
        self.assertEqual((first["lesson"], first["subject"], first["doctorId"], first["batch"]),
                         (f"telegram-q:{M}:L01", "physiology", "dr-omar-qassem-phys", "58"))
        self.assertEqual(data["questions"][1]["batch"], "59")
        self.assertEqual(first["stats"], {"attempts": 10, "correct": 7})
        self.assertTrue(first["source_id"].startswith("bank:"))
        self.assertEqual(data["lessons"], [{"key": f"telegram-q:{M}:L01", "subject": "physiology", "name": "Pain control",
                                            "order": 1, "chapter": {"title": "Central Nervous System", "order": 1,
                                                                    "existing": False}}])
        self.assertEqual(data["module"], "cns")

    def test_a_doctor_of_another_subject_is_dropped(self):
        data, _ = importfile.build(M, [q("ok")], [lab("ok")], LECTURES, {"Omar Qasem": "dr-x-anat"})
        self.assertIsNone(data["questions"][0]["doctorId"])


if __name__ == "__main__":
    unittest.main()
