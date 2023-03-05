import os
import cv2
import openai
import random
from string import ascii_uppercase
from time import sleep
from dotenv import load_dotenv
from ppadb.client import Client
from pytesseract import pytesseract


def wait_for_device():
    """Waits for a device to be connected via USB and returns it."""
    print("📲 Connecting to ADB...")
    adb = Client(host='127.0.0.1', port=5037)
    devices = adb.devices()

    if (not len(devices)):
        print('📵 No device found! Retrying in 5s...\n')
        sleep(5)
        return wait_for_device()

    print('📱 Connected!\n')
    return devices[0]


def delete_screenshots():
    """Deletes all images in the 'screenshots' directory."""
    dir = './screenshots'
    for f in os.listdir(dir):
        if f != ".gitkeep":
            os.remove(os.path.join(dir, f))


def parse_slice_dimensions(dim):
    """Parses the given slice dimenions to a 2D array and returns it."""
    return [[int(x[0]), int(x[1])] for x in (wh.split(":") for wh in dim.split("-"))]


def calc_slice_center(s):
    """Calculates the center coordinates (x|y) of the given slice and returns it."""
    return [(s[1][0] + s[1][1]) / 2, (s[0][0] + s[0][1]) / 2]


def extract_texts(img, slices, lang):
    """Extracts the texts in the given image slices and returns them."""
    images = [img[s[0][0]:s[0][1], s[1][0]:s[1][1]] for s in slices]

    texts = []
    for idx, img in enumerate(images):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cv2.imwrite('./screenshots/img_{}_gray.jpg'.format(idx), gray)

        ret, thresh1 = cv2.threshold(
            gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)
        cv2.imwrite('./screenshots/img_{}_tresh.jpg'.format(idx), thresh1)

        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 12))
        dilation = cv2.dilate(thresh1, rect_kernel, iterations=3)
        cv2.imwrite('./screenshots/img_{}_dilation.jpg'.format(idx), dilation)

        contours, _ = cv2.findContours(
            dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        im2 = img.copy()

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)

            # Draw the bounding box on the text area
            rect = cv2.rectangle(im2, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Crop the bounding box area
            cropped = im2[y:y + h, x:x + w]

            cv2.imwrite('./screenshots/img_{}.jpg'.format(idx), rect)

            # Using tesseract on the cropped image area to get text
            text = pytesseract.image_to_string(
                cropped, lang=lang)
            text = text.replace("\n", " ").replace("  ", " ").strip()

            if (len(text)):
                texts.append(text)

    return texts


def prompt_chatgpt(question, gpt_key):
    """Prompts a question to the ChatGPT API and returns the answer."""
    openai.api_key = gpt_key
    completions = openai.ChatCompletion.create(
        model=os.getenv('GPT_MODEL'),
        messages=[{'role': 'user', 'content': question}]
    )

    return completions.choices[0].message.content.strip()


if __name__ == '__main__':
    load_dotenv()

    # ADB setup
    device = wait_for_device()

    # Build slices & calculate answer center coordinates
    ANSWERS_CENTER = {}
    SLICES = [parse_slice_dimensions(os.getenv('SLICE_Q'))]

    for char in ascii_uppercase:
        if os.getenv('SLICE_ANSW_' + char) is None:
            break

        s = parse_slice_dimensions(os.getenv('SLICE_ANSW_' + char))

        SLICES.append(s)
        ANSWERS_CENTER[char] = calc_slice_center(s)

    TOUCH_RANDOMNESS = int(os.getenv('TOUCH_RANDOMNESS'))

    input('❓ Open a question and and press <Enter> to start...')

    while (True):

        print('\n----------------------------------')

        delete_screenshots()

        print('\n📸 Taking screenshot...')
        screenshot = device.screencap()

        with open('./screenshots/screen.jpg', 'wb') as f:
            f.write(screenshot)

        src = cv2.imread('./screenshots/screen.jpg')

        print('\n📋 Extracting texts...')
        texts = extract_texts(src, SLICES, os.getenv('TESSERACT_LANG'))
        print(texts)

        if (len(texts) != len(SLICES)):
            print('😟 Could not recognize all texts!')
            answer = input('Enter alternative answer: ').upper()
        else:
            # Build question string with possible answers
            question = texts[0]

            for i, answ in enumerate(texts[1:]):
                question += " {}: {}?".format(ascii_uppercase[i], answ)

            question += " " + ", ".join(ANSWERS_CENTER.keys()) + "?"

            # Ask ChatGPT
            print('\n🧠 Asking ChatGPT...')
            message = prompt_chatgpt(question, os.getenv('GPT_KEY'))
            print('🙋 Answer given: ' + message)

            answer = message[0]

            if (not answer in ANSWERS_CENTER):
                print('😟 No definite answer found!')
                answer = input('Enter alternative answer: ').upper()

        print('\n👆 Entering answer: {}'.format(answer))
        [x, y] = ANSWERS_CENTER.get(answer)

        # Adding randomness
        rnd = random.randint(-TOUCH_RANDOMNESS, TOUCH_RANDOMNESS)
        device.input_tap(x + rnd, y + rnd)

        input('\nPress <Enter> to continue...')
