import unittest

from claudish.screen import opens_above


class OpensAbove(unittest.TestCase):
    """A panel goes under its line, above it only when it does not fit below and above has more room."""

    def test_fits_below(self):
        self.assertFalse(opens_above(200, below=300, above=600))

    def test_low_on_the_screen(self):
        self.assertTrue(opens_above(200, below=80, above=700))

    def test_too_tall_for_either_side_stays_where_there_is_more_room(self):
        self.assertFalse(opens_above(900, below=500, above=300))  # a drafts panel mid-screen: not off the top
        self.assertTrue(opens_above(900, below=300, above=500))


if __name__ == "__main__":
    unittest.main()
