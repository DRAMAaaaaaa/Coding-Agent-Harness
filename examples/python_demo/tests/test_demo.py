import unittest

import demo


class DemoTest(unittest.TestCase):
    def test_value_is_two(self) -> None:
        self.assertEqual(demo.VALUE, 2)


if __name__ == "__main__":
    unittest.main()
