import unittest

import msk_quizzes as M


class Clean(unittest.TestCase):
    def test_numbering_letters_and_bullets_are_not_question_text(self):
        self.assertEqual(M.clean("[1/6] Nissl granules:", ["a", "b"]), ("Nissl granules:", ["a", "b"]))
        self.assertEqual(M.clean("3. CSF is secreted by:", ["A Choroid plexus", "B Arachnoid villi"]),
                         ("CSF is secreted by:", ["Choroid plexus", "Arachnoid villi"]))
        self.assertEqual(M.clean("Action of infraspinatus?", ["- Medially rotates", "- Abducts"])[1],
                         ["Medially rotates", "Abducts"])

    def test_letters_out_of_order_stay(self):
        self.assertEqual(M.clean("Q", ["B vitamin", "A cell"])[1], ["B vitamin", "A cell"])

    def test_every_item_names_a_known_doctor_and_lessons(self):
        for post, (doctor, title, lessons, own) in M.ITEMS.items():
            self.assertTrue(doctor.startswith("dr-"), post)
            self.assertTrue(lessons and all(x.startswith("L") for x in lessons), post)
            self.assertTrue(all(x.startswith("lecture:y1-") for x in own), post)


if __name__ == "__main__":
    unittest.main()
