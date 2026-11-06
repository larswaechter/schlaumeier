import os
from dotenv import load_dotenv
from main import check_tesseract, wait_for_device, delete_screenshots, take_screenshot, load_slices, extract_texts

load_dotenv()

check_tesseract()

# Text area slices [[hFrom, hTo], [wFrom, wTo]]
SLICES, _ = load_slices()

# ADB setup
device = wait_for_device()

delete_screenshots()
src = take_screenshot(device)
texts = extract_texts(src, SLICES, os.getenv('TESSERACT_LANG', 'eng'))

print(texts)
print('Cropping finished! Check "screenshots" directory.')
