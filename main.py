import sys
import os
import cv2
import openai
from time import sleep
from dotenv import load_dotenv
from ppadb.client import Client
from pytesseract import pytesseract

load_dotenv()

# ADB setup
def wait_for_device():
    print("📲 Connecting to ADB...")
    adb = Client(host="127.0.0.1", port=5037)
    devices = adb.devices()

    if(not len(devices)):
        print("📵 No device found! Retrying in 5s...\n")
        sleep(5)
        return wait_for_device()
    
    print("📱 Connected!\n")
    return devices[0]

device = wait_for_device()

# Answers' center coordinates [x, y]
ANSW_A = [int(x) for x in os.getenv('COORD_ANSW_A').split("-")]
ANSW_D = [int(x) for x in os.getenv('COORD_ANSW_D').split("-")]
ANSW_B = [ANSW_D[0], ANSW_A[1]]
ANSW_C = [ANSW_A[0], ANSW_D[1]]

ANSWERS_COORD = {
    "A": ANSW_A,
    "B": ANSW_B,
    "C": ANSW_C,
    "D": ANSW_D
}

# Text area slices [[hFrom, hTo], [wFrom, wTo]]
SLICE_Q = [int(x) for x in os.getenv('SLICE_Q').split(":")]
SLICE_ANSW_A = [[int(x[0]), int(x[1])] for x in (wh.split(":") for wh in os.getenv('SLICE_ANSW_A').split("-"))]
SLICE_ANSW_D = [[int(x[0]), int(x[1])] for x in (wh.split(":") for wh in os.getenv('SLICE_ANSW_D').split("-"))]
SLICE_ANSW_B = [SLICE_ANSW_A[0], SLICE_ANSW_D[1]]
SLICE_ANSW_C = [SLICE_ANSW_D[0], SLICE_ANSW_A[1]]

SLICES = [
    SLICE_ANSW_A, SLICE_ANSW_B, SLICE_ANSW_C, SLICE_ANSW_D
]

while(True):

    # Delete screenshots
    dir = './screenshots'
    for f in os.listdir(dir):
        if f != ".gitkeep":
            os.remove(os.path.join(dir, f))

    print("📸 Taking screenshot...")
    screenshot = device.screencap()

    with open("./screenshots/screen.jpg", "wb") as f:
        f.write(screenshot)

    src = cv2.imread("./screenshots/screen.jpg")
    # cv2.imwrite('croppy.jpg', src[500:1400, :])

    [dHeight, dWidth, _] = src.shape

    # Cropped areas (y|x)
    img_q = src[SLICE_Q[0]:SLICE_Q[1], :]
    images = [img_q]

    for _slice in SLICES:
        images.append(src[_slice[0][0]:_slice[0][1], _slice[1][0]:_slice[1][1]])

    texts = []
    print("\n📋 Extracting texts...")
    for idx, img in enumerate(images):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cv2.imwrite('./screenshots/img_{}_gray.jpg'.format(idx), gray)

        ret, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)
        cv2.imwrite('./screenshots/img_{}_tresh.jpg'.format(idx), thresh1)

        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 12))
        dilation = cv2.dilate(thresh1, rect_kernel, iterations = 3)
        cv2.imwrite('./screenshots/img_{}_dilation.jpg'.format(idx),dilation)

        contours, hierarchy = cv2.findContours(dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        im2 = img.copy()

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Draw the bounding box on the text area
            rect=cv2.rectangle(im2, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # Crop the bounding box area
            cropped = im2[y:y + h, x:x + w]
            
            cv2.imwrite('./screenshots/img_{}.jpg'.format(idx),rect)
            
            # Using tesseract on the cropped image area to get text
            text = pytesseract.image_to_string(cropped, lang='eng') #, config='--psm 12')
            text = text.replace("\n", " ").replace("  ", " ").strip()

            if(len(text)):
                texts.append(text)

    if(not len(texts) == 5):
        print("😟 Could not recognize texts")
        answer = input('Enter alternative answer: ').upper()
    else:
        # Build question string with possible answers
        question = texts[0]
        question += " A: " + texts[1]
        question += "? B: " + texts[2]
        question += "? C: " + texts[3]
        question += "? D: " + texts[4]
        question += "? A, B, C or D?"

        print(texts)

        # Ask ChatGPT
        print("\n🧠 Asking ChatGPT...")
        openai.api_key = os.getenv('GPT_KEY')
        completions = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": question}]
        )

        message = completions.choices[0].message.content.strip()
        print("🙋 Answer given: " + message)

        answer = message[0:1]

        if(not answer in ANSWERS_COORD):
            print("😟 No definite answer found")
            answer = input('Enter alternative answer: ').upper()

    print("\n👆 Entering answer: {}".format(answer))
    [x, y] = ANSWERS_COORD.get(answer)
    device.input_tap(x, y)

    input("\nPress any key to continue...")
    print("----------------------------------\n")

    # Continue to next question
    device.input_tap(dWidth / 2, dHeight / 2)
    sleep(1.5)