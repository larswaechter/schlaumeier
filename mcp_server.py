import os
import cv2
import numpy as np
from collections import namedtuple
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from ppadb.client import Client

# Longest image side of a screenshot
SCREENSHOT_MAX_SIZE = 1024

# The size of a screenshot and its scale relative to the device resolution
Screenshot = namedtuple('Screenshot', ['width', 'height', 'scale'])

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


def scale_screenshot(data):
    """Scales a raw screenshot down and returns it as JPEG, together with its size."""
    if (not data):
        raise ToolError('The device returned an empty screenshot.')

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)

    if (img is None):
        raise ToolError('The screenshot could not be decoded.')

    scale = min(1, SCREENSHOT_MAX_SIZE / max(img.shape[:2]))

    if (scale < 1):
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)

    _, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])

    return jpg.tobytes(), Screenshot(img.shape[1], img.shape[0], scale)


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

    jpg, last_screenshot = scale_screenshot(get_device().screencap())

    return ['Screenshot size: {}x{}'.format(last_screenshot.width, last_screenshot.height),
            Image(data=jpg, format='jpeg')]


@mcp.tool()
def tap(x: int, y: int) -> str:
    """Taps the phone at the given coordinates on the last screenshot."""
    device_x, device_y = to_device_coordinates(x, y, last_screenshot)
    get_device().input_tap(device_x, device_y)

    return 'Tapped ({}, {}) on the device.'.format(device_x, device_y)


if __name__ == '__main__':
    mcp.run(transport='stdio')
