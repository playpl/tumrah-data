import unittest

from spine.questions import grades


def q(sid, lesson, doctor, stem="Which nerve supplies the deltoid muscle?", options=("Axillary", "Radial", "Ulnar"), quiz=False):
    return {"source_id": sid, "lesson": lesson, "doctorId": doctor, "stem": stem, "options": list(options),
            "appearances": [{"source_type": "doctor_quiz"}] if quiz else [{"source_type": "telegram_poll"}]}


LESSONS = {"lecture:a": "dr-a", "lecture:b": "dr-a", "lecture:c": "dr-a"}


class Grades(unittest.TestCase):
    def rows(self, questions, more=()):
        return {r["source_id"]: r for r in grades.grade(questions, LESSONS, more)}

    def test_the_owners_grades(self):
        r = self.rows([
            q("form:1", "lecture:a", "dr-a", stem="s1"),                 # his own quiz
            q("mcq:x:p1:1", "lecture:a", "dr-a", stem="s2"),             # his file, lecture a has his quiz
            q("mcq:x:p1:2", "lecture:b", "dr-a", stem="s3"),             # his file, no quiz from him on b
            q("mcq:y:p1:1", "lecture:c", "dr-b", stem="s4"),             # another doctor's file
            q("bank:1", "lecture:c", "dr-a", stem="s5", quiz=True),      # a Telegram quiz he posted
            q("bank:2", "lecture:c", None, stem="s6"),                   # a poll
            q("old:1", "lecture:c", None, stem="s7")])
        self.assertEqual({k: v["grade"] for k, v in r.items()},
                         {"form:1": 1, "mcq:x:p1:1": 2, "mcq:x:p1:2": 1, "mcq:y:p1:1": 3, "bank:1": 1, "bank:2": 4, "old:1": 5})

    def test_a_file_question_finds_its_poll_for_votes(self):
        r = self.rows([q("mcq:x:p1:1", "lecture:a", "dr-a", stem="Q3. Which nerve supplies the deltoid muscle ?"),
                       q("bank:9", "lecture:a", None, stem="Which nerve supplies the deltoid muscle?")])
        self.assertEqual(r["mcq:x:p1:1"]["poll"], "bank:9")
        self.assertNotIn("poll", r["bank:9"])

    def test_a_poll_off_the_site_still_gives_votes_and_other_options_never_match(self):
        more = [{"source_id": "poll:Batch58ATM:5", "stem": "Q: Which nerve supplies the deltoid muscle?",
                 "options": ["Axillary", "Radial", "Ulnar"]}]
        r = self.rows([q("own:1", "lecture:a", "dr-a"), q("own:2", "lecture:a", "dr-a", options=("A", "B", "C"))], more)
        self.assertEqual(r["own:1"]["poll"], "poll:Batch58ATM:5")
        self.assertIsNone(r["own:2"]["poll"])


if __name__ == "__main__":
    unittest.main()
