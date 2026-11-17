import unittest
from unittest import mock

import outline


class OwnCutter(unittest.TestCase):
    def test_a_module_with_cut_py_is_never_recut_by_page(self):
        with mock.patch.object(outline, "build", side_effect=AssertionError("build must not run")):
            with self.assertRaises(RuntimeError) as e:
                outline.write("year1-musculoskeletal")
        self.assertIn("cut.py build", str(e.exception))


if __name__ == "__main__":
    unittest.main()
