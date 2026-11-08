import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import merge  # noqa: E402


def row(q, opts, key=None, votes=None, total=0, **s):
    sight = {"source": "poll", "chat": "Batch58ATM", "msg_id": 1, "date": None, "header": None, "doctor": None, "link": None}
    sight.update(s)
    return {"question": q, "options": opts, "key": key, "solution": None, "votes": votes or [0] * len(opts),
            "total": total, "sightings": [sight]}


class TestMerge(unittest.TestCase):
    def test_channel_repeats_add_votes_and_never_raise_importance(self):
        bank = merge.merge([row("Q?", ["Yes", "No"], 0, [5, 1], 6, chat="Batch58ATM", msg_id=4),
                            row("Q?", ["No", "Yes"], 1, [2, 4], 6, chat="zagpolls58", msg_id=9)])
        self.assertEqual(len(bank), 1)
        q = bank[0]
        self.assertEqual((q["votes"], q["total"], q["key"], q["key_conflict"]), ([9, 3], 12, 0, False))
        self.assertEqual((q["repetition_count"], q["importance_score"]), (1, 1))
        self.assertEqual(len(q["sightings"]), 2)

    def test_doctor_repeats_raise_importance(self):
        bank = merge.merge([row("Q?", ["a", "b"], 0, doctor="Dr A"), row("Q?", ["a", "b"], 0, doctor="Dr B"),
                            row("Q?", ["a", "b"], 0, doctor="Dr A", chat="other")])
        self.assertEqual((bank[0]["repetition_count"], bank[0]["importance_score"], bank[0]["doctors"]), (2, 2, ["Dr A", "Dr B"]))

    def test_one_changed_word_is_a_new_question(self):
        self.assertEqual(len(merge.merge([row("The nerve of the arm", ["a", "b"]), row("The nerve of the leg", ["a", "b"])])), 2)

    def test_different_keys_are_a_conflict_never_a_choice(self):
        q = merge.merge([row("Q?", ["a", "b"], 0), row("Q?", ["a", "b"], 1)])[0]
        self.assertTrue(q["key_conflict"])
        self.assertEqual(q["key"], 0)

    def test_only_the_owner_settles_a_conflict(self):
        bank = merge.merge([row("Q?", ["a", "b"], 0), row("Q?", ["a", "b"], 1), row("R?", ["a", "b"], 0)])
        merge.apply_decisions(bank, {bank[0]["word_key"]: {"key": 1}, bank[1]["word_key"]: {"key": 1}})
        self.assertEqual((bank[0]["key"], bank[0]["key_conflict"], bank[0]["key_source"]), (1, False, "owner"))
        self.assertEqual((bank[1]["key"], "key_source" in bank[1]), (0, False))  # no conflict: the source key stays

    def test_a_source_rows_own_conflict_survives(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "q.jsonl"
            p.write_text(json.dumps({"question": "Q?", "options": ["a", "b"], "key": 0, "votes": [1, 1], "total": 2,
                                     "key_conflict": True, "sightings": [{"chat": "c", "msg_id": 1}]}) + "\n", encoding="utf-8")
            self.assertTrue(merge.merge(merge.load_polls(p))[0]["key_conflict"])

    def test_telegram_links(self):
        self.assertEqual(merge.telegram_link("Batch58ATM", 12), "https://t.me/Batch58ATM/12")
        self.assertEqual(merge.telegram_link("id2516282829", 3), "https://t.me/c/2516282829/3")
        self.assertIsNone(merge.telegram_link(None, 3))

    def test_quizbot_labels_are_stripped(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            qp, lp = Path(tmp) / "q.jsonl", Path(tmp) / "l.jsonl"
            qp.write_text(json.dumps({"param": "P1", "question": "[2/10] Q?", "options": ["A) a", "B) b"], "correct_index": 1}) + "\n")
            lp.write_text(json.dumps({"param": "P1", "sightings": [{"chat": "zmsu", "msg_id": 5, "chat_doctor": "Dr C"}]}) + "\n")
            rows = merge.load_quizbot(qp, lp)
        self.assertEqual((rows[0]["question"], rows[0]["options"], rows[0]["sightings"][0]["doctor"]), ("Q?", ["a", "b"], "Dr C"))
        self.assertEqual(merge.merge(rows + [row("Q?", ["a", "b"], 1)])[0]["key_conflict"], False)


if __name__ == "__main__":
    unittest.main()
