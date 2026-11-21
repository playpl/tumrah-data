import unittest

import msk_questions as M


class Headers(unittest.TestCase):
    def test_pointing_hand_and_case_are_normalised(self):
        self.assertEqual(M.norm_header("👇 Histology of Bone"), "histology of bone")
        self.assertEqual(M.HEADERS[M.norm_header("👇🏻 Pectoral Region")], ["L01"])
        self.assertEqual(M.norm_header("📌 Case Q22:"), "case q22:")

    def test_every_header_names_known_lessons(self):
        for h, ls in M.HEADERS.items():
            self.assertTrue(ls and all(x in M.ALL for x in ls), h)


if __name__ == "__main__":
    unittest.main()
