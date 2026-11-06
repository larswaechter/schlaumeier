import os
import re
import sys
import base64
import cv2
import openai
import random
import anthropic
from collections import namedtuple
from string import ascii_uppercase
from time import sleep
from dotenv import load_dotenv
from ppadb.client import Client
from pytesseract import pytesseract

SYSTEM_PROMPT = (
    'You answer multiple-choice quiz questions. '
    'Reply with only the letter of the correct answer.'
)

VISION_PROMPT = (
    'Answer the quiz question on this screenshot. '
    'Each possible answer is marked with its letter in a black box.'
)

# Longest image side sent to the LLM when using the 'vision' screen reader
VISION_MAX_SIZE = 1024

# With 'vision' the LLM reads the screenshot itself, otherwise it gets the Tesseract texts
LLM = namedtuple('LLM', ['client', 'model', 'vision'])


def require_env(name):
    """Returns the given environment variable or exits if it is not set."""
    value = os.getenv(name)

    if (not value):
        sys.exit('😟 Missing environment variable: {}'.format(name))

    return value


def create_openai_client(url):
    """Creates a client for a server with an OpenAI compatible API."""
    # These servers usually don't check the API key, but the client requires one.
    # Loading a local model can take a while.
    return openai.OpenAI(base_url=url, api_key=os.getenv('CUSTOM_KEY') or 'none',
                         timeout=120)


def create_llm():
    """Creates the LLM for the provider and screen reader set in the environment."""
    provider = os.getenv('LLM_PROVIDER', 'openai').lower()
    reader = os.getenv('SCREEN_READER', 'tesseract').lower()

    if (reader not in ('tesseract', 'vision')):
        sys.exit('😟 Unknown SCREEN_READER: {}'.format(reader))

    vision = reader == 'vision'

    if (provider == 'openai'):
        client = openai.OpenAI(api_key=require_env('GPT_KEY'), timeout=30)
        return LLM(client, require_env('GPT_MODEL'), vision)

    if (provider == 'ollama'):
        client = create_openai_client(
            os.getenv('OLLAMA_URL', 'http://localhost:11434/v1'))
        return LLM(client, require_env('OLLAMA_MODEL'), vision)

    if (provider == 'anthropic'):
        client = anthropic.Anthropic(
            api_key=require_env('ANTHROPIC_API_KEY'), timeout=30)
        return LLM(client, require_env('ANTHROPIC_MODEL'), vision)

    if (provider == 'custom'):
        client = create_openai_client(require_env('CUSTOM_URL'))
        return LLM(client, require_env('CUSTOM_MODEL'), vision)

    sys.exit('😟 Unknown LLM_PROVIDER: {}'.format(provider))


def check_tesseract():
    """Exits if Tesseract is not installed."""
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        sys.exit("😟 Tesseract is not installed! It's required by SCREEN_READER=tesseract and cropper.py --ocr.")


def wait_for_device():
    """Waits for a device to be connected via USB and returns it."""
    print("📲 Connecting to ADB...")
    adb = Client(host='127.0.0.1', port=5037)

    while (True):
        try:
            devices = adb.devices()
        except RuntimeError:
            print('🖥️  ADB server not reachable! Retrying in 5s...\n')
            sleep(5)
            continue

        if (len(devices)):
            print('📱 Connected!\n')
            return devices[0]

        print('📵 No device found! Retrying in 5s...\n')
        sleep(5)


def delete_screenshots():
    """Deletes all images in the 'screenshots' directory."""
    dir = './screenshots'
    for f in os.listdir(dir):
        if f != ".gitkeep":
            os.remove(os.path.join(dir, f))


def take_screenshot(device):
    """Takes a screenshot of the given device, saves it and returns the image."""
    with open('./screenshots/screen.jpg', 'wb') as f:
        f.write(device.screencap())

    return cv2.imread('./screenshots/screen.jpg')


def parse_slice_dimensions(dim):
    """Parses the given slice dimenions to a 2D array and returns it."""
    return [[int(x[0]), int(x[1])] for x in (wh.split(":") for wh in dim.split("-"))]


def calc_slice_center(s):
    """Calculates the center coordinates (x|y) of the given slice and returns it."""
    return [(s[1][0] + s[1][1]) / 2, (s[0][0] + s[0][1]) / 2]


def load_slices():
    """Builds the slices from the environment and calculates the answer center coordinates."""
    slices = [parse_slice_dimensions(require_env('SLICE_Q'))]
    answers_center = {}

    for char in ascii_uppercase:
        if os.getenv('SLICE_ANSW_' + char) is None:
            break

        s = parse_slice_dimensions(os.getenv('SLICE_ANSW_' + char))

        slices.append(s)
        answers_center[char] = calc_slice_center(s)

    return slices, answers_center


def extract_texts(img, slices, lang):
    """Extracts the text of each given image slice and returns them in the same order.

    A slice without any recognized text results in an empty string.
    """
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

        # OpenCV returns the contours from bottom to top => Restore reading order
        boxes = sorted((cv2.boundingRect(cnt) for cnt in contours),
                       key=lambda box: (box[1], box[0]))

        im2 = img.copy()
        parts = []

        for x, y, w, h in boxes:
            # Draw the bounding box on the text area
            cv2.rectangle(im2, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Crop the bounding box area
            cropped = img[y:y + h, x:x + w]

            # Using tesseract on the cropped image area to get text
            text = pytesseract.image_to_string(cropped, lang=lang)

            # Clean text
            text = " ".join(text.split())

            if (len(text)):
                parts.append(text)

        cv2.imwrite('./screenshots/img_{}.jpg'.format(idx), im2)
        texts.append(" ".join(parts))

    return texts


def build_question(texts):
    """Builds the prompt from the question text followed by the possible answers."""
    answers = ["{}: {}".format(ascii_uppercase[i], answ)
               for i, answ in enumerate(texts[1:])]

    return "\n".join([texts[0]] + answers)


def parse_answer(message, letters):
    """Returns the answer letter the given message starts with or None if there is none."""
    match = re.match(r'\W*([A-Z])\b', message)

    if (match and match.group(1) in letters):
        return match.group(1)

    return None


def ask_alternative_answer(letters):
    """Asks the user for an answer until it is valid. Returns None if it's skipped."""
    while (True):
        answer = input('Enter alternative answer (empty to skip): ').strip().upper()

        if (not answer):
            return None

        if (answer in letters):
            return answer

        print('😟 Invalid answer! Choose from: ' + ", ".join(letters))


def draw_label(img, char, s):
    """Draws a letter in the top left corner of the given slice."""
    y, x = s[0][0], s[1][0]
    cv2.rectangle(img, (x, y), (x + 70, y + 70), (0, 0, 0), -1)
    cv2.putText(img, char, (x + 14, y + 55), cv2.FONT_HERSHEY_SIMPLEX,
                1.8, (255, 255, 255), 4, cv2.LINE_AA)


def build_vision_image(img, slices, answers_center):
    """Returns the screenshot with a letter on each answer slice as base64 encoded JPEG."""
    img = img.copy()

    for char, s in zip(answers_center, slices[1:]):
        draw_label(img, char, s)

    # Crop the image to the question and answers
    img = img[min(s[0][0] for s in slices):max(s[0][1] for s in slices),
              min(s[1][0] for s in slices):max(s[1][1] for s in slices)]

    scale = VISION_MAX_SIZE / max(img.shape[:2])
    if (scale < 1):
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)

    cv2.imwrite('./screenshots/img_vision.jpg', img)

    _, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(jpg.tobytes()).decode()


def prompt_openai(llm, prompt, image):
    """Sends a prompt to an OpenAI compatible API and returns the answer."""
    content = prompt

    if (image is not None):
        url = 'data:image/jpeg;base64,' + image
        content = [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': url}}
        ]

    completions = llm.client.chat.completions.create(
        model=llm.model,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': content}
        ]
    )

    return completions.choices[0].message.content or ''


def prompt_anthropic(llm, prompt, image):
    """Sends a prompt to the Claude API and returns the answer."""
    content = [{'type': 'text', 'text': prompt}]

    if (image is not None):
        content.insert(0, {
            'type': 'image',
            'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': image}
        })

    response = llm.client.messages.create(
        model=llm.model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': content}]
    )

    # A refused request has no text, which results in no definite answer
    return "".join(b.text for b in response.content if b.type == 'text')


def prompt_llm(llm, prompt, image=None):
    """Sends a prompt and an optional image to the LLM and returns the answer."""
    if (isinstance(llm.client, anthropic.Anthropic)):
        return prompt_anthropic(llm, prompt, image).strip()

    return prompt_openai(llm, prompt, image).strip()


def solve_question(device, llm, slices, answers_center, lang):
    """Takes a screenshot, finds the answer to the question and returns it."""
    delete_screenshots()

    print('\n📸 Taking screenshot...')
    src = take_screenshot(device)

    if (llm.vision):
        prompt = VISION_PROMPT
        image = build_vision_image(src, slices, answers_center)
    else:
        print('\n📋 Extracting texts...')
        texts = extract_texts(src, slices, lang)
        print(texts)

        if (not all(texts)):
            print('😟 Could not recognize all texts!')
            return ask_alternative_answer(answers_center)

        prompt = build_question(texts)
        image = None

    print('\n🧠 Asking {}...'.format(llm.model))
    try:
        message = prompt_llm(llm, prompt, image)
    except (openai.OpenAIError, anthropic.AnthropicError) as e:
        print('😟 Request to {} failed: {}'.format(llm.model, e))
        return ask_alternative_answer(answers_center)

    print('🙋 Answer given: ' + message)
    answer = parse_answer(message, answers_center)

    if (answer is None):
        print('😟 No definite answer found!')
        return ask_alternative_answer(answers_center)

    return answer


def main():
    load_dotenv()

    llm = create_llm()

    if (not llm.vision):
        check_tesseract()

    lang = os.getenv('TESSERACT_LANG', 'eng')
    touch_randomness = int(os.getenv('TOUCH_RANDOMNESS', 0))

    # Build slices & calculate answer center coordinates
    slices, answers_center = load_slices()

    # ADB setup
    device = wait_for_device()

    input('❓ Open a question and press <Enter> to start...')

    while (True):

        print('\n----------------------------------')

        answer = solve_question(device, llm, slices, answers_center, lang)

        if (answer is not None):
            print('\n👆 Entering answer: {}'.format(answer))
            [x, y] = answers_center[answer]

            # Adding randomness
            rnd = random.randint(-touch_randomness, touch_randomness)
            device.input_tap(x + rnd, y + rnd)

        input('\nPress <Enter> to continue...')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n👋 Bye!')
