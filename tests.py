import cv2
import unittest
from collections import namedtuple

from main import calc_slice_center, parse_slices, extract_texts

# Devices Screen Slices
SLICES = namedtuple('Device', [
                    'SLICE_Q', 'SLICE_ANSW_A', 'SLICE_ANSW_B', 'SLICE_ANSW_C', 'SLICE_ANSW_D'])
SLICES_G1 = SLICES("700:1400-0:1080", "1465:1775-65:515",
                   '1465:1775-565:1015', '1825:2135-65:515', "1825:2135-565:1015")


class TestExtract(unittest.TestCase):
    def test_calc_slice_center(self):
        self.assertEqual(calc_slice_center(
            [[200, 400], [700, 1000]]), [850.0, 300.0])

    def test_build_slices(self):
        slices = parse_slices([
            SLICES_G1.SLICE_Q,
            SLICES_G1.SLICE_ANSW_A,
            SLICES_G1.SLICE_ANSW_B,
            SLICES_G1.SLICE_ANSW_C,
            SLICES_G1.SLICE_ANSW_D
        ])

        self.assertEqual(len(slices), 5)
        self.assertEqual(len(slices[0]), 2)
        self.assertEqual(len(slices[1]), 2)
        self.assertEqual(len(slices[2]), 2)
        self.assertEqual(len(slices[3]), 2)
        self.assertEqual(len(slices[4]), 2)

        # Question slice
        self.assertEqual(slices[0][0][0], 700)
        self.assertEqual(slices[0][0][1], 1400)
        self.assertEqual(slices[0][1][0], 0)
        self.assertEqual(slices[0][1][1], 1080)

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

    # def test_question_1(self):
    #     slices = parse_slices([
    #         SLICES_G1.SLICE_Q,
    #         SLICES_G1.SLICE_ANSW_A,
    #         SLICES_G1.SLICE_ANSW_B,
    #         SLICES_G1.SLICE_ANSW_C,
    #         SLICES_G1.SLICE_ANSW_D
    #     ])

    #     img = cv2.imread("./tests/question_1.jpg")
    #     texts = extract_texts(img, slices)

    #     self.assertEqual(len(texts), 5)
    #     self.assertEqual(
    #         texts[0], 'In which European capital can you find the fine arts museums known as the "Petit Palais" and the "Grand Palais"?')
    #     self.assertEqual(texts[1], 'London')
    #     self.assertEqual(texts[2], 'Paris')
    #     self.assertEqual(texts[3], 'Madrid')

    # def test_question_2(self):
    #     slices = parse_slices([
    #         SLICES_G1.SLICE_Q,
    #         SLICES_G1.SLICE_ANSW_A,
    #         SLICES_G1.SLICE_ANSW_B,
    #         SLICES_G1.SLICE_ANSW_C,
    #         SLICES_G1.SLICE_ANSW_D
    #     ])

    #     img = cv2.imread("./tests/question_2.jpg")
    #     texts = extract_texts(img, slices)

    #     self.assertEqual(len(texts), 5)
    #     self.assertEqual(texts[0], 'Who wrote the sci-fi book "Neuromancer"?')
    #     self.assertEqual(texts[1], 'Arthur C. Clarke')
    #     self.assertEqual(texts[2], 'William Gibson')
    #     self.assertEqual(texts[3], 'Gregory Benford')
    #     self.assertEqual(texts[4], 'Anthony Burgess')

    # def test_question_3(self):
    #     slices = parse_slices([
    #         SLICES_G1.SLICE_Q,
    #         SLICES_G1.SLICE_ANSW_A,
    #         SLICES_G1.SLICE_ANSW_B,
    #         SLICES_G1.SLICE_ANSW_C,
    #         SLICES_G1.SLICE_ANSW_D
    #     ])

    #     img = cv2.imread("./tests/question_3.jpg")
    #     texts = extract_texts(img, slices)

    #     self.assertEqual(len(texts), 5)
    #     self.assertEqual(texts[0], 'Who was known as the Roman god of wine?')
    #     self.assertEqual(texts[1], 'Janus')
    #     self.assertEqual(texts[2], 'Jupiter')
    #     self.assertEqual(texts[3], 'Bacchus')
    #     self.assertEqual(texts[4], 'Neptune')

    # def test_question_4(self):
    #     slices = parse_slices([
    #         SLICES_G2.SLICE_Q,
    #         SLICES_G2.SLICE_ANSW_A,
    #         SLICES_G2.SLICE_ANSW_B,
    #         SLICES_G2.SLICE_ANSW_C,
    #         SLICES_G2.SLICE_ANSW_D
    #     ])

    #     img = cv2.imread("./tests/question_4.jpg")
    #     texts = extract_texts(img, slices)

    #     self.assertEqual(len(texts), 5)
    #     self.assertEqual(
    #         texts[0], 'What is a group of people that travels through the desert on camels?')
    #     self.assertEqual(texts[1], 'Cordovan')
    #     self.assertEqual(texts[2], 'Caravan')
    #     self.assertEqual(texts[3], 'Catamaran')
    #     self.assertEqual(texts[4], 'Mulligan')


if __name__ == '__main__':
    unittest.main()
