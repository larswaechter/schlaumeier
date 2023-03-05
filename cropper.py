import os
from cv2 import imread
from dotenv import load_dotenv
from main import wait_for_device, delete_screenshots, parse_slices, extract_texts

load_dotenv()

# ADB setup
device = wait_for_device()

# Text area slices [[hFrom, hTo], [wFrom, wTo]]
SLICES = parse_slices([
    os.getenv('SLICE_Q'),
    os.getenv('SLICE_ANSW_A'),
    os.getenv('SLICE_ANSW_B'),
    os.getenv('SLICE_ANSW_C'),
    os.getenv('SLICE_ANSW_D')
])

delete_screenshots()
screenshot = device.screencap()

with open('./screenshots/screen.jpg', 'wb') as f:
    f.write(screenshot)

src = imread('./screenshots/screen.jpg')
texts = extract_texts(src, SLICES, os.getenv('TESSERACT_LANG'))

print('Cropping finished! Check "screenshots" directory.')
