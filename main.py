import sys
import os
import cv2
import openai
from dotenv import load_dotenv
from ppadb.client import Client
from pytesseract import pytesseract

load_dotenv()

# Connect to ADB
print("Connecting to ADB...")
adb = Client(host="127.0.0.1", port=5037)
devices = adb.devices()

if(not len(devices)):
    print("No device attached!")
    quit()

# Delete screenshots
dir = './screenshots'
for f in os.listdir(dir):
    os.remove(os.path.join(dir, f))

# Make screenshot

print("Making screenshot...")
device = devices[0]
screenshot = device.screencap()

with open("./screenshots/screen.jpg", "wb") as f:
    f.write(screenshot)

src = cv2.imread("./screenshots/screen.jpg")
# cv2.imwrite('croppy.jpg', src[500:1400, :])

ANSWERS_COORD = {
    "A": [300, 1600],
    "B": [800, 1600],
    "C": [300, 1900],
    "D": [800, 1900]
}

# Cropped images
img_q = src[700:1400, :]
img_a1 = src[1465:1775, 65:515]
img_a2 = src[1465:1775, 565:1015]
img_a3 = src[1825:2135, 65:515]
img_a4 = src[1825:2135, 565:1015]

texts = []
images = [img_q, img_a1, img_a2, img_a3, img_a4]

print("Extracting texts...")
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

# Build question with possible answers
question = texts[0]
question += " A: " + texts[1]
question += "? B: " + texts[2]
question += "? C: " + texts[3]
question += "? D: " + texts[4]
question += "? A, B, C or D?"

print(texts)

# Ask ChatGPT
openai.api_key = os.getenv('GPT_KEY')
completions = openai.Completion.create(
    engine="text-davinci-003",
    prompt=question,
    max_tokens=50,
    n=1,
    stop=None,
    temperature=0.5,
)

message = completions.choices[0].text.strip()
print(message, "input=" + message[0:1])

answer = message[0:1]

if(not answer in ANSWERS_COORD):
    print(("No clear answer found!"))
    quit()

# Simulate touch
[x, y] = ANSWERS_COORD.get(answer)
device.shell("input tap {} {}".format(x, y))