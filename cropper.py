import os
import sys
import cv2
from string import ascii_uppercase
from dotenv import load_dotenv
from main import check_tesseract, draw_label, wait_for_device, delete_screenshots, take_screenshot, load_slices, extract_texts


def draw_slices(img, slices):
    """Returns a copy of the image with a labeled rectangle on each slice."""
    img = img.copy()

    for char, s in zip('Q' + ascii_uppercase, slices):
        cv2.rectangle(img, (s[1][0], s[0][0]), (s[1][1], s[0][1]),
                      (0, 255, 0), 4)
        draw_label(img, char, s)

    return img


def find_invalid_slices(img, slices):
    """Returns the labels of all slices that are empty or exceed the image."""
    height, width = img.shape[:2]

    return [char for char, s in zip('Q' + ascii_uppercase, slices)
            if not (0 <= s[0][0] < s[0][1] <= height and 0 <= s[1][0] < s[1][1] <= width)]


if __name__ == '__main__':
    load_dotenv()

    ocr = '--ocr' in sys.argv[1:]

    if (ocr):
        check_tesseract()

    # Text area slices [[hFrom, hTo], [wFrom, wTo]]
    slices, _ = load_slices()

    # ADB setup
    device = wait_for_device()

    delete_screenshots()
    src = take_screenshot(device)

    cv2.imwrite('./screenshots/slices.jpg', draw_slices(src, slices))
    print('Check your slices in "screenshots/slices.jpg".')

    invalid = find_invalid_slices(src, slices)

    if (invalid):
        print('😟 Invalid slices on this {}x{} screen: {}'.format(
            src.shape[1], src.shape[0], ', '.join(invalid)))

    if (ocr):
        print(extract_texts(src, slices, os.getenv('TESSERACT_LANG', 'eng')))
