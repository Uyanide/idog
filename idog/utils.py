import base64
import os
import random
import zlib
import struct
import fcntl
import array
import termios
import sys
from PIL import Image


def random_ID(max: int = 0xFFFFFF) -> int: return random.randint(0, max)
def base64_encode(data: bytes) -> str: return base64.b64encode(data).decode("ascii")
def zlib_compress(data: bytes) -> bytes: return zlib.compress(data)


def png_makechunk(type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + type + data + struct.pack(">I", zlib.crc32(type + data, 0))


def mock_png_data(width: int, height: int) -> bytes:
    data = b"\x89PNG\r\n\x1a\n"
    # IHDR
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data += png_makechunk(b"IHDR", ihdr)
    # IDAT
    compressor = zlib.compressobj(level=9, strategy=zlib.Z_DEFAULT_STRATEGY)
    idat = compressor.compress(b"".join(
        b"\x00" + b"\xff\xff\xff\x80" * width for _ in range(height)
    )) + compressor.flush()
    data += png_makechunk(b"IDAT", idat)
    # IEND
    data += png_makechunk(b"IEND", b"")
    return data


class NoInteractiveTerminalError(Exception):
    pass


def atty_fd() -> int:
    """Return a file descriptor for an active terminal, or raise an exception if none found"""
    for fd in (sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()):
        if os.isatty(fd):
            return fd
    raise NoInteractiveTerminalError("No active terminal found")


def terminal_dimensions() -> tuple[int, int, int, int]:
    """Obtain terminal dimensions (columns, rows) via ioctl"""
    buf = array.array('H', [0, 0, 0, 0])
    fcntl.ioctl(atty_fd(), termios.TIOCGWINSZ, buf)
    rows, cols, x_pixels, y_pixels = buf
    if 0 in (rows, cols, x_pixels, y_pixels):
        raise RuntimeError("Failed to get terminal dimensions")
    return cols, rows, x_pixels, y_pixels


def smart_resize(image: Image.Image,
                 display_cols: int, display_rows: int,
                 cell_width: int, cell_height: int,
                 max_cols: int, max_rows: int) -> Image.Image:
    """
    Resize the image to fit within the specified display dimensions

    :param image:
        The image to resize
    :type image: Image.Image
    :param display_cols:
        The exact number of columns of the resized image.
        If positive, the image will be stretched to fit this width.
        If zero or negative, the width will be as large as possible while respecting the other constraints.
    :type display_cols: int
    :param display_rows:
        The exact number of rows of the resized image.
        If positive, the image will be stretched to fit this height.
        If zero or negative, the height will be as large as possible while respecting the other constraints.
    :type display_rows: int
    :param cell_width:
        The width of a character cell in pixels.
        Set to 1 for pixel-perfect resizing, or a larger value to resize based on character cell dimensions.
        Also used as the minimum width of the resized image.
    :type cell_width: int
    :param cell_height:
        The height of a character cell in pixels.
        Set to 1 for pixel-perfect resizing, or a larger value to resize based on character cell dimensions.
        Also used as the minimum height of the resized image.
    :type cell_height: int
    :param max_cols:
        The maximum number of columns of the resized image.
        If positive, the image will be resized to fit within this width if it would otherwise exceed
        If zero or negative, this constraint is ignored.
    :type max_cols: int
    :param max_rows:
        The maximum number of rows of the resized image.
        If positive, the image will be resized to fit within this height if it would otherwise exceed
        If zero or negative, this constraint is ignored.
    :type max_rows: int
    :return:
        The resized image
    :rtype: Image
    """
    if cell_height <= 0 or cell_width <= 0:
        raise ValueError("Cell dimensions must be positive")
    image_width, image_height = image.size
    image_aspect = image_width / image_height

    resized_width = image_width
    resized_height = image_height
    # Both specified, stretch to fit
    if display_cols > 0 and display_rows > 0:
        resized_width = int(display_cols * cell_width)
        resized_height = int(display_rows * cell_height)
    # Only width specified
    elif display_cols > 0:
        # If max_rows is specified, repect the constraint
        # even if stretching is needed to fit the width
        if max_rows > 0:
            max_height = int(max_rows * cell_height)
            resized_width = int(display_cols * cell_width)
            resized_height = int(resized_width / image_aspect)
            if resized_height > max_height:
                resized_height = max_height
        else:
            resized_width = int(display_cols * cell_width)
            resized_height = int(resized_width / image_aspect)
    # Only height specified
    elif display_rows > 0:
        # If max_cols is specified, repect the constraint
        # even if stretching is needed to fit the height
        if max_cols > 0:
            max_width = int(max_cols * cell_width)
            resized_height = int(display_rows * cell_height)
            resized_width = int(resized_height * image_aspect)
            if resized_width > max_width:
                resized_width = max_width
        else:
            resized_height = int(display_rows * cell_height)
            resized_width = int(resized_height * image_aspect)
    # Neither specified
    else:
        # If max_cols and max_rows are both specified, fit within the constraints
        if max_cols > 0 and max_rows > 0:
            max_width = int(max_cols * cell_width)
            max_height = int(max_rows * cell_height)
            if image_aspect > (max_width / max_height):
                resized_width = min(image_width, max_width)
                resized_height = int(resized_width / image_aspect)
            else:
                resized_height = min(image_height, max_height)
                resized_width = int(resized_height * image_aspect)
        # Only max_cols specified, fit to width
        elif max_cols > 0:
            max_width = int(max_cols * cell_width)
            resized_width = min(image_width, max_width)
            resized_height = int(resized_width / image_aspect)
        # Only max_rows specified, fit to height
        elif max_rows > 0:
            max_height = int(max_rows * cell_height)
            resized_height = min(image_height, max_height)
            resized_width = int(resized_height * image_aspect)
        # Neither specified, keep original size
        else:
            resized_width = image_width
            resized_height = image_height

        # If original image is smaller than the resized dimensions, keep original size
        if image_width <= resized_width and image_height <= resized_height:
            resized_width = image_width
            resized_height = image_height

    if resized_width < cell_width:
        resized_width = cell_width
    if resized_height < cell_height:
        resized_height = cell_height

    display_cols = int(resized_width / cell_width)
    display_rows = int(resized_height / cell_height)
    return image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
