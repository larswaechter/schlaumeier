import cv2
import base64
import shutil
import unittest
import numpy as np
from collections import namedtuple
from difflib import SequenceMatcher
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
import mcp_server
from main import build_question, calc_slice_center, extract_texts, parse_answer, parse_slice_dimensions

# Minimum similarity of an OCR result, since the output differs slightly between Tesseract versions
MIN_OCR_SIMILARITY = 0.9

# Devices Screen Slices
SLICES = namedtuple('Device', [
                    'SLICE_Q', 'SLICE_ANSW_A', 'SLICE_ANSW_B', 'SLICE_ANSW_C', 'SLICE_ANSW_D'])
SLICES_G1 = SLICES("700:1400-0:1080", "1465:1775-65:515",
                   '1465:1775-565:1015', '1825:2135-65:515', "1825:2135-565:1015")
SLICES_G2 = SLICES("300:1000-0:1080", "1040:1280-50:1020",
                   "1335:1575-50:1020", "1630:1870-50:1020", "1925:2165-50:1020")

QUESTIONS = [
    ('./tests/question_1.jpg', SLICES_G1, [
        'In which European capital can you find the fine arts museums known as the "Petit Palais" and the "Grand Palais"?',
        'London', 'Paris', 'Madrid', 'Berlin']),
    ('./tests/question_2.jpg', SLICES_G1, [
        'Who wrote the sci-fi book "Neuromancer"?',
        'Arthur C. Clarke', 'William Gibson', 'Gregory Benford', 'Anthony Burgess']),
    ('./tests/question_3.jpg', SLICES_G1, [
        'Who was known as the Roman god of wine?',
        'Janus', 'Jupiter', 'Bacchus', 'Neptune']),
    ('./tests/question_4.jpg', SLICES_G2, [
        'What is a group of people that travels through the desert on camels?',
        'Cordovan', 'Caravan', 'Catamaran', 'Mulligan']),
]


def parse_slices(device_slices):
    return [parse_slice_dimensions(s) for s in device_slices]


def fake_llm(content='A', vision=False):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content=content))])

    return main.LLM(client, 'model', vision)


class TestSlices(unittest.TestCase):
    def test_calc_slice_center(self):
        self.assertEqual(calc_slice_center(
            [[200, 400], [700, 1000]]), [850.0, 300.0])

    def test_parse_slice_dimensions(self):
        slices = parse_slices(SLICES_G1)

        self.assertEqual(len(slices), 5)
        self.assertEqual(slices[0], [[700, 1400], [0, 1080]])
        self.assertEqual(slices[1], [[1465, 1775], [65, 515]])
        self.assertEqual(slices[2], [[1465, 1775], [565, 1015]])
        self.assertEqual(slices[3], [[1825, 2135], [65, 515]])
        self.assertEqual(slices[4], [[1825, 2135], [565, 1015]])

    def test_load_slices(self):
        env = {'SLICE_Q': '0:10-0:10', 'SLICE_ANSW_A': '10:20-0:10',
               'SLICE_ANSW_B': '20:30-0:10', 'SLICE_ANSW_C': '30:40-0:10'}

        with patch.dict('os.environ', env, clear=True):
            slices, answers_center = main.load_slices()

        self.assertEqual(len(slices), 4)
        self.assertEqual(list(answers_center), ['A', 'B', 'C'])
        self.assertEqual(answers_center['B'], [5.0, 25.0])


class TestAnswer(unittest.TestCase):
    def test_build_question(self):
        self.assertEqual(build_question(['Which one?', 'Sitar', 'Marimba']),
                         'Which one?\nA: Sitar\nB: Marimba')

    def test_parse_answer(self):
        for message in ['B', 'B.', 'B: Marimba', '**B**', '(B) Marimba']:
            self.assertEqual(parse_answer(message, 'ABCD'), 'B', message)

    def test_parse_answer_without_definite_answer(self):
        for message in ['', 'The answer is B', 'Sorry', 'E', 'E: Sitar', '...']:
            self.assertIsNone(parse_answer(message, 'ABCD'), message)

    def test_ask_alternative_answer(self):
        with patch('builtins.input', side_effect=['x', 'nope', ' b ']):
            self.assertEqual(main.ask_alternative_answer({'A': 0, 'B': 1}), 'B')

    def test_ask_alternative_answer_skip(self):
        with patch('builtins.input', return_value=''):
            self.assertIsNone(main.ask_alternative_answer({'A': 0}))

    def test_prompt_llm(self):
        llm = fake_llm(content=' B\n')

        self.assertEqual(main.prompt_llm(llm, 'Q'), 'B')

        kwargs = llm.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'model')
        self.assertEqual(kwargs['messages'][-1],
                         {'role': 'user', 'content': 'Q'})

    def test_prompt_llm_with_image(self):
        llm = fake_llm()
        main.prompt_llm(llm, 'Q', 'aW1n')

        kwargs = llm.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['messages'][-1]['content'], [
            {'type': 'text', 'text': 'Q'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,aW1n'}}
        ])

    def test_prompt_llm_empty_content(self):
        self.assertEqual(main.prompt_llm(fake_llm(content=None), 'Q'), '')


class TestAnthropic(unittest.TestCase):
    def llm(self, blocks):
        client = MagicMock(spec=main.anthropic.Anthropic)
        client.messages = MagicMock()
        client.messages.create.return_value = SimpleNamespace(content=blocks)

        return main.LLM(client, 'claude', False)

    def text(self, text):
        return SimpleNamespace(type='text', text=text)

    def test_prompt(self):
        llm = self.llm([self.text(' B\n')])

        self.assertEqual(main.prompt_llm(llm, 'Q'), 'B')

        kwargs = llm.client.messages.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'claude')
        self.assertEqual(kwargs['system'], main.SYSTEM_PROMPT)
        self.assertGreater(kwargs['max_tokens'], 0)
        self.assertEqual(kwargs['messages'], [
            {'role': 'user', 'content': [{'type': 'text', 'text': 'Q'}]}])

    def test_prompt_with_image(self):
        llm = self.llm([self.text('B')])
        main.prompt_llm(llm, 'Q', 'aW1n')

        content = llm.client.messages.create.call_args.kwargs['messages'][0]['content']
        self.assertEqual(content, [
            {'type': 'image', 'source': {
                'type': 'base64', 'media_type': 'image/jpeg', 'data': 'aW1n'}},
            {'type': 'text', 'text': 'Q'}
        ])

    def test_only_text_blocks_are_read(self):
        llm = self.llm([SimpleNamespace(type='thinking', thinking='hmm'),
                        self.text('C')])

        self.assertEqual(main.prompt_llm(llm, 'Q'), 'C')

    def test_refusal_has_no_text(self):
        self.assertEqual(main.prompt_llm(self.llm([]), 'Q'), '')

    def test_refusal_falls_back_to_user(self):
        with patch.object(main, 'delete_screenshots'), \
                patch.object(main, 'take_screenshot'), \
                patch.object(main, 'extract_texts', return_value=['Q', 'x', 'y']), \
                patch('builtins.input', return_value='b'):
            self.assertEqual(main.solve_question(
                MagicMock(), self.llm([]), [], {'A': 0, 'B': 1}, 'eng'), 'B')

    def test_failed_request_falls_back_to_user(self):
        llm = self.llm([])
        llm.client.messages.create.side_effect = main.anthropic.AnthropicError(
            'boom')

        with patch.object(main, 'delete_screenshots'), \
                patch.object(main, 'take_screenshot'), \
                patch.object(main, 'extract_texts', return_value=['Q', 'x', 'y']), \
                patch('builtins.input', return_value='b'):
            self.assertEqual(main.solve_question(
                MagicMock(), llm, [], {'A': 0, 'B': 1}, 'eng'), 'B')


class TestProvider(unittest.TestCase):
    OPENAI = {'GPT_KEY': 'key', 'GPT_MODEL': 'gpt'}
    OLLAMA = {'LLM_PROVIDER': 'ollama', 'OLLAMA_MODEL': 'local'}
    ANTHROPIC = {'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_API_KEY': 'key',
                 'ANTHROPIC_MODEL': 'claude'}
    CUSTOM = {'LLM_PROVIDER': 'custom', 'CUSTOM_URL': 'http://example.test:1234/v1',
              'CUSTOM_MODEL': 'other'}

    def create(self, env):
        with patch.dict('os.environ', env, clear=True):
            return main.create_llm()

    def test_openai_is_default(self):
        llm = self.create(self.OPENAI)

        self.assertEqual(llm.model, 'gpt')
        self.assertIn('api.openai.com', str(llm.client.base_url))

    def test_ollama(self):
        llm = self.create(self.OLLAMA)

        self.assertEqual(llm.model, 'local')
        self.assertIn('localhost:11434', str(llm.client.base_url))

    def test_ollama_custom_url(self):
        llm = self.create({**self.OLLAMA,
                           'OLLAMA_URL': 'http://example.test:1234/v1'})

        self.assertIn('example.test:1234', str(llm.client.base_url))

    def test_anthropic(self):
        llm = self.create(self.ANTHROPIC)

        self.assertEqual(llm.model, 'claude')
        self.assertIsInstance(llm.client, main.anthropic.Anthropic)

    def test_custom(self):
        llm = self.create(self.CUSTOM)

        self.assertEqual(llm.model, 'other')
        self.assertIn('example.test:1234', str(llm.client.base_url))
        self.assertEqual(llm.client.api_key, 'none')

    def test_custom_key(self):
        llm = self.create({**self.CUSTOM, 'CUSTOM_KEY': 'secret'})

        self.assertEqual(llm.client.api_key, 'secret')

    def test_tesseract_is_default_reader(self):
        for env in [self.OPENAI, self.OLLAMA, self.ANTHROPIC, self.CUSTOM]:
            self.assertFalse(self.create(env).vision)

    def test_screen_reader_works_with_every_provider(self):
        for env in [self.OPENAI, self.OLLAMA, self.ANTHROPIC, self.CUSTOM]:
            self.assertFalse(
                self.create({**env, 'SCREEN_READER': 'tesseract'}).vision)
            self.assertTrue(
                self.create({**env, 'SCREEN_READER': 'vision'}).vision)
            self.assertTrue(
                self.create({**env, 'SCREEN_READER': 'VISION'}).vision)

    def test_missing_setting(self):
        for env in [{}, {'GPT_KEY': 'key'}, {'LLM_PROVIDER': 'ollama'},
                    {'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_API_KEY': 'key'},
                    {'LLM_PROVIDER': 'anthropic', 'ANTHROPIC_MODEL': 'claude'},
                    {'LLM_PROVIDER': 'custom', 'CUSTOM_URL': 'http://x/v1'},
                    {'LLM_PROVIDER': 'custom', 'CUSTOM_MODEL': 'other'}]:
            with self.assertRaises(SystemExit):
                self.create(env)

    def test_unknown_provider(self):
        with self.assertRaises(SystemExit):
            self.create({'LLM_PROVIDER': 'nope'})

    def test_unknown_screen_reader(self):
        with self.assertRaises(SystemExit):
            self.create({**self.OPENAI, 'SCREEN_READER': 'nope'})


class TestCheckTesseract(unittest.TestCase):
    def test_installed(self):
        with patch.object(main.pytesseract, 'get_tesseract_version'):
            main.check_tesseract()

    def test_not_installed(self):
        error = main.pytesseract.TesseractNotFoundError()

        with patch.object(main.pytesseract, 'get_tesseract_version', side_effect=error):
            with self.assertRaises(SystemExit):
                main.check_tesseract()


class TestVisionPrompt(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(main.cv2, 'imwrite')
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, img, slices):
        answers_center = {char: calc_slice_center(s) for char, s in
                          zip('ABCD', slices[1:])}
        image = main.build_vision_image(img, slices, answers_center)

        jpg = np.frombuffer(base64.b64decode(image), np.uint8)
        return cv2.imdecode(jpg, cv2.IMREAD_COLOR)

    def test_image_is_cropped_and_scaled(self):
        decoded = self.build(cv2.imread('./tests/question_1.jpg'),
                             parse_slices(SLICES_G1))

        self.assertEqual(max(decoded.shape[:2]), main.VISION_MAX_SIZE)
        self.assertAlmostEqual(decoded.shape[1] / decoded.shape[0],
                               1080 / (2135 - 700), places=1)

    def test_small_image_is_not_upscaled(self):
        img = np.full((200, 200, 3), 255, np.uint8)
        decoded = self.build(img, [[[0, 100], [0, 200]],
                                   [[100, 200], [0, 200]]])

        self.assertEqual(decoded.shape[:2], (200, 200))

    def test_letters_are_drawn_on_answer_slices_only(self):
        img = np.full((400, 400, 3), 255, np.uint8)
        decoded = self.build(img, [[[0, 100], [0, 400]],
                                   [[100, 250], [0, 400]],
                                   [[250, 400], [0, 400]]])

        self.assertGreater(decoded[0:90, 0:70].mean(), 250)
        self.assertLess(decoded[105:165, 5:65].mean(), 128)
        self.assertLess(decoded[255:315, 5:65].mean(), 128)

    def test_input_image_is_not_changed(self):
        img = np.full((200, 200, 3), 255, np.uint8)
        self.build(img, [[[0, 100], [0, 200]], [[100, 200], [0, 200]]])

        self.assertEqual(img.min(), 255)


class TestSolveQuestion(unittest.TestCase):
    def solve(self, texts, llm):
        with patch.object(main, 'delete_screenshots'), \
                patch.object(main, 'take_screenshot'), \
                patch.object(main, 'extract_texts', return_value=texts) as self.ocr, \
                patch.object(main, 'build_vision_image', return_value='aW1n'), \
                patch('builtins.input', return_value='b'):
            return main.solve_question(MagicMock(), llm, [],
                                       {'A': 0, 'B': 1}, 'eng')

    def test_answer_from_llm(self):
        self.assertEqual(self.solve(['Q', 'x', 'y'], fake_llm(content='A')), 'A')

    def test_vision_llm_skips_ocr(self):
        llm = fake_llm(content='A', vision=True)

        self.assertEqual(self.solve(['Q', '', ''], llm), 'A')
        self.ocr.assert_not_called()

    def test_missing_text_falls_back_to_user(self):
        llm = fake_llm()

        self.assertEqual(self.solve(['Q', '', 'y'], llm), 'B')
        llm.client.chat.completions.create.assert_not_called()

    def test_failed_request_falls_back_to_user(self):
        llm = fake_llm()
        llm.client.chat.completions.create.side_effect = main.openai.OpenAIError(
            'boom')

        self.assertEqual(self.solve(['Q', 'x', 'y'], llm), 'B')


class TestExtract(unittest.TestCase):
    """Tests the image pipeline with a fake OCR, independent of the installed Tesseract."""

    def setUp(self):
        patcher = patch.object(main.cv2, 'imwrite')
        patcher.start()
        self.addCleanup(patcher.stop)

    def extract(self, img, slices, ocr):
        with patch.object(main.pytesseract, 'image_to_string', side_effect=ocr) as mock:
            return extract_texts(img, slices, 'eng'), mock

    def blank_image(self):
        return np.full((300, 300, 3), 255, np.uint8)

    def test_one_text_per_slice(self):
        img = cv2.imread('./tests/question_1.jpg')
        texts, _ = self.extract(
            img, parse_slices(SLICES_G1), lambda *a, **k: 'text')

        self.assertEqual(len(texts), 5)

    def test_empty_slice_keeps_position(self):
        img = self.blank_image()
        img[210:240, 50:150] = 0

        texts, _ = self.extract(
            img, [[[0, 100], [0, 300]], [[200, 300], [0, 300]]], lambda *a, **k: 'text')

        self.assertEqual(texts, ['', 'text'])

    def test_blocks_are_joined_in_reading_order(self):
        img = self.blank_image()
        img[20:40, 50:150] = 0
        img[220:240, 50:250] = 0

        # The blocks differ in width, which tells them apart
        def ocr(cropped, lang):
            return 'top' if cropped.shape[1] < 150 else 'bottom'

        texts, _ = self.extract(img, [[[0, 300], [0, 300]]], ocr)

        self.assertEqual(texts, ['top bottom'])

    def test_text_is_normalized(self):
        img = self.blank_image()
        img[20:40, 50:150] = 0

        texts, _ = self.extract(
            img, [[[0, 100], [0, 300]]], lambda *a, **k: ' one\ntwo   three\n\n')

        self.assertEqual(texts, ['one two three'])

    def test_bounding_box_is_not_passed_to_ocr(self):
        img = self.blank_image()
        img[20:40, 50:150] = 0
        img[120:140, 50:150] = 0

        _, mock = self.extract(
            img, [[[0, 300], [0, 300]]], lambda *a, **k: 'text')

        for call in mock.call_args_list:
            b, g, r = cv2.split(call.args[0])
            self.assertFalse(((g == 255) & (b == 0) & (r == 0)).any())


class TestMcpServer(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(mcp_server, 'last_screenshot', None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.device = MagicMock()
        patcher = patch.object(mcp_server, 'get_device',
                               return_value=self.device)
        patcher.start()
        self.addCleanup(patcher.stop)

    def screencap(self, width, height):
        _, png = cv2.imencode('.png', np.zeros((height, width, 3), np.uint8))
        self.device.screencap.return_value = png.tobytes()

    def test_screenshot_is_scaled(self):
        self.screencap(1080, 2340)
        text, image = mcp_server.get_screenshot()

        self.assertEqual(max(mcp_server.last_screenshot[:2]),
                         mcp_server.SCREENSHOT_MAX_SIZE)
        self.assertEqual(text, 'Screenshot size: 473x1024')
        self.assertEqual(cv2.imdecode(np.frombuffer(image.data, np.uint8),
                                      cv2.IMREAD_COLOR).shape[:2], (1024, 473))

    def test_small_screenshot_is_not_upscaled(self):
        self.screencap(320, 480)
        mcp_server.get_screenshot()

        self.assertEqual(mcp_server.last_screenshot,
                         mcp_server.Screenshot(320, 480, 1))

    def test_landscape_screenshot(self):
        self.screencap(2340, 1080)
        mcp_server.get_screenshot()

        self.assertEqual(mcp_server.last_screenshot[:2], (1024, 473))

    def test_tap_is_scaled_to_device(self):
        self.screencap(1080, 2340)
        mcp_server.get_screenshot()
        mcp_server.tap(236, 512)

        self.device.input_tap.assert_called_once_with(539, 1170)

    def test_tap_on_small_screenshot_is_not_scaled(self):
        self.screencap(320, 480)
        mcp_server.get_screenshot()
        mcp_server.tap(100, 200)

        self.device.input_tap.assert_called_once_with(100, 200)

    def test_tap_requires_screenshot(self):
        with self.assertRaises(mcp_server.ToolError):
            mcp_server.tap(10, 10)

        self.device.input_tap.assert_not_called()

    def test_tap_outside_of_screenshot(self):
        self.screencap(1080, 2340)
        mcp_server.get_screenshot()

        for x, y in [(-1, 10), (10, -1), (473, 10), (10, 1024)]:
            with self.assertRaises(mcp_server.ToolError):
                mcp_server.tap(x, y)

        self.device.input_tap.assert_not_called()

    def test_invalid_screenshot(self):
        for data in [b'', b'no image']:
            self.device.screencap.return_value = data

            with self.assertRaises(mcp_server.ToolError):
                mcp_server.get_screenshot()


class TestMcpDevice(unittest.TestCase):
    def devices(self, serials, env={}):
        devices = [SimpleNamespace(serial=serial) for serial in serials]

        with patch.object(mcp_server, 'Client') as client, \
                patch.dict('os.environ', env, clear=True):
            client.return_value.devices.return_value = devices
            return mcp_server.get_device()

    def test_single_device(self):
        self.assertEqual(self.devices(['a']).serial, 'a')

    def test_no_device(self):
        with self.assertRaises(mcp_server.ToolError):
            self.devices([])

    def test_multiple_devices_are_not_guessed(self):
        with self.assertRaises(mcp_server.ToolError):
            self.devices(['a', 'b'])

    def test_serial_selects_device(self):
        self.assertEqual(self.devices(['a', 'b'], {'ADB_SERIAL': 'b'}).serial, 'b')

    def test_unknown_serial(self):
        with self.assertRaises(mcp_server.ToolError):
            self.devices(['a'], {'ADB_SERIAL': 'b'})


@unittest.skipUnless(shutil.which('tesseract'), 'Tesseract is not installed')
class TestOCR(unittest.TestCase):
    """Tests the recognized texts of real screenshots."""

    def setUp(self):
        patcher = patch.object(main.cv2, 'imwrite')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_questions(self):
        for path, device_slices, expected in QUESTIONS:
            with self.subTest(path):
                texts = extract_texts(cv2.imread(path),
                                      parse_slices(device_slices), 'eng')

                self.assertEqual(len(texts), len(expected))

                for text, exp in zip(texts, expected):
                    similarity = SequenceMatcher(None, text, exp).ratio()
                    self.assertGreaterEqual(
                        similarity, MIN_OCR_SIMILARITY, '{!r} != {!r}'.format(text, exp))


if __name__ == '__main__':
    unittest.main()
