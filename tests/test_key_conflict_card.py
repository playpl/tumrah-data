"""The answer-key card counts only the module's own undecided conflicts (owner works on CNS only)."""
import json
import tempfile
import unittest
from pathlib import Path

import decisions


class ModuleKeyConflicts(unittest.TestCase):
    def test_only_pointed_and_undecided(self):
        d = Path(tempfile.mkdtemp())
        rows = [{"word_key": "cns1", "key_conflict": True}, {"word_key": "cns2", "key_conflict": True},
                {"word_key": "msk1", "key_conflict": True}, {"word_key": "cns3", "key_conflict": False}]
        (d / "q.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (d / "p.json").write_text(json.dumps({"cns1": {}, "cns2": {}, "cns3": {}}), encoding="utf-8")
        (d / "k.json").write_text(json.dumps({"cns2": 1}), encoding="utf-8")
        self.assertEqual(decisions.module_key_conflicts("m", d / "q.jsonl", d / "p.json", d / "k.json"), 1)

    def test_missing_files(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(decisions.module_key_conflicts("m", d / "none.jsonl", d / "none.json"), 0)


if __name__ == "__main__":
    unittest.main()
