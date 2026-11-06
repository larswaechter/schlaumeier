import os
import cv2
import numpy as np
from collections import namedtuple
from time import monotonic
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from ppadb.client import Client

# Longest image side of a screenshot
SCREENSHOT_MAX_SIZE = 768

# A screen has new content if this share of its pixels changed by more than the
# brightness threshold. Highlighted answers and animated backgrounds stay far below.
CHANGE_BRIGHTNESS = 80
CHANGE_AREA = 0.01

# Seconds to wait for the next screen after a tap
TAP_TIMEOUT = 10

# A scaled image, its size and its scale relative to the device resolution
Screenshot = namedtuple('Screenshot', ['image', 'width', 'height', 'scale'])

mcp = MCPServer('schlaumeier')

# The screenshot that tap coordinates refer to
last_screenshot = None


def get_device():
    """Returns the connected device, selected by 'ADB_SERIAL' if there are multiple."""
    try:
        devices = Client(host='127.0.0.1', port=5037).devices()
    except RuntimeError:
        raise ToolError('ADB server not reachable. Run "adb start-server".')

    serial = os.getenv('ADB_SERIAL')
    serials = [device.serial for device in devices]

    if (serial):
        if (serial not in serials):
            raise ToolError(
                'Device {} not found. Connected: {}'.format(serial, serials))

        return devices[serials.index(serial)]

    if (not devices):
        raise ToolError('No device found. Check "adb devices".')

    if (len(devices) > 1):
        raise ToolError(
            'Multiple devices connected: {}. Set ADB_SERIAL.'.format(serials))

    return devices[0]


def take_screenshot(device):
    """Takes a screenshot of the given device and scales it down."""
    data = device.screencap()

    if (not data):
        raise ToolError('The device returned an empty screenshot.')

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    if (img is None):
        raise ToolError('The screenshot could not be decoded.')

    scale = min(1, SCREENSHOT_MAX_SIZE / max(img.shape[:2]))

    if (scale < 1):
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)

    return Screenshot(img, img.shape[1], img.shape[0], scale)


def has_new_content(before, after):
    """Returns whether the content of two images differs, ignoring highlights."""
    if (before.shape != after.shape):
        return True

    diff = cv2.absdiff(cv2.cvtColor(before, cv2.COLOR_BGR2GRAY),
                       cv2.cvtColor(after, cv2.COLOR_BGR2GRAY))

    return np.mean(diff > CHANGE_BRIGHTNESS) > CHANGE_AREA


def wait_for_next_screen(device, before):
    """Waits for new content to settle. Returns the screenshot and whether it changed."""
    deadline = monotonic() + TAP_TIMEOUT
    previous = before
    changed = False

    while (monotonic() < deadline):
        current = take_screenshot(device)
        moved = has_new_content(previous.image, current.image)

        if (changed and not moved):
            return current, True

        changed = changed or moved
        previous = current

    return previous, changed


def to_tool_result(text, screenshot):
    """Returns the given text and screenshot as a result of a tool."""
    _, jpg = cv2.imencode('.jpg', screenshot.image,
                          [cv2.IMWRITE_JPEG_QUALITY, 90])

    return ['{} Screenshot size: {}x{}'.format(text, screenshot.width, screenshot.height),
            Image(data=jpg.tobytes(), format='jpeg')]


def to_device_coordinates(x, y, screenshot):
    """Converts coordinates on the given screenshot to device coordinates."""
    if (screenshot is None):
        raise ToolError('Call get_screenshot before tapping.')

    if (not (0 <= x < screenshot.width and 0 <= y < screenshot.height)):
        raise ToolError('({}, {}) is outside of the {}x{} screenshot.'.format(
            x, y, screenshot.width, screenshot.height))

    return round(x / screenshot.scale), round(y / screenshot.scale)


@mcp.tool()
def get_screenshot():
    """Takes a screenshot of the phone. Returns its size and the image."""
    global last_screenshot

    last_screenshot = take_screenshot(get_device())

    return to_tool_result('Current screen.', last_screenshot)


@mcp.tool()
def tap(x: int, y: int):
    """Taps the phone at the given coordinates on the last screenshot.

    Waits for the next screen and returns it like get_screenshot, so that no further
    screenshot is required. Highlighting a tapped button doesn't count as a new screen.
    """
    global last_screenshot

    device_x, device_y = to_device_coordinates(x, y, last_screenshot)
    device = get_device()
    device.input_tap(device_x, device_y)

    last_screenshot, changed = wait_for_next_screen(device, last_screenshot)

    return to_tool_result('New screen.' if changed else 'Screen unchanged after {}s.'.format(TAP_TIMEOUT),
                          last_screenshot)


if __name__ == '__main__':
    mcp.run(transport='stdio')
