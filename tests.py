import cv2
import unittest
from collections import namedtuple

from main import build_slices, extract_texts

# Devices Screen Slices
DEVICE = namedtuple('Device', ['SLICE_Q', 'SLICE_ANSW_A', 'SLICE_ANSW_D'])
DEVICE_REDMI_NOTE7 = DEVICE("700:1400", "1465:1775-65:515", "1825:2135-565:1015")

class TestSum(unittest.TestCase):
    def test_build_slices(self):
        slices = build_slices(DEVICE_REDMI_NOTE7.SLICE_Q, DEVICE_REDMI_NOTE7.SLICE_ANSW_A, DEVICE_REDMI_NOTE7.SLICE_ANSW_D)

        self.assertEqual(len(slices), 5)
        self.assertEqual(len(slices[0]), 1)
        self.assertEqual(len(slices[1]), 2)
        self.assertEqual(len(slices[2]), 2)
        self.assertEqual(len(slices[3]), 2)
        self.assertEqual(len(slices[4]), 2)

        # Question slice
        self.assertEqual(slices[0][0][0], 700)
        self.assertEqual(slices[0][0][1], 1400)

        # Answer A slice
        self.assertEqual(slices[1][0][0], 1465)
        self.assertEqual(slices[1][0][1], 1775)
        self.assertEqual(slices[1][1][0], 65)
        self.assertEqual(slices[1][1][1], 515)

        # Answer B slice
        self.assertEqual(slices[2][0][0], 1465)
        self.assertEqual(slices[2][0][1], 1775)
        self.assertEqual(slices[2][1][0], 565)
        self.assertEqual(slices[2][1][1], 1015)

        # Answer C slice
        self.assertEqual(slices[3][0][0], 1825)
        self.assertEqual(slices[3][0][1], 2135)
        self.assertEqual(slices[3][1][0], 65)
        self.assertEqual(slices[3][1][1], 515)

        # Answer D slice
        self.assertEqual(slices[4][0][0], 1825)
        self.assertEqual(slices[4][0][1], 2135)
        self.assertEqual(slices[4][1][0], 565)
        self.assertEqual(slices[4][1][1], 1015)


    def test_question_1(self):
        slices = build_slices(DEVICE_REDMI_NOTE7.SLICE_Q, DEVICE_REDMI_NOTE7.SLICE_ANSW_A, DEVICE_REDMI_NOTE7.SLICE_ANSW_D)
        img = cv2.imread("./questions/question_1.jpg")
        texts = extract_texts(img, slices)

        self.assertEqual(len(texts), 5)
        self.assertEqual(texts[0], 'In which European capital can you find the fine arts museums known as the "Petit Palais” and the "Grand Palais"?')
        self.assertEqual(texts[1], 'London')
        self.assertEqual(texts[2], 'Paris')
        self.assertEqual(texts[3], 'Madrid')
        self.assertEqual(1, 1)


if __name__ == '__main__':
    unittest.main()