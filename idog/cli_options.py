import argparse
import logging
from pathlib import Path
import sys

from idog.query import KGPQuery
from idog.utils import random_ID, terminal_dimensions
from idog.constants import KGP_UNICODE_MAX_SIZE, KGP_TRANSMISSION_MEDIUM


class ArgParseError(Exception):
    pass


class KGPOptions:
    path: Path

    display_cols: int
    display_rows: int
    max_cols: int
    max_rows: int
    cell_width: int
    cell_height: int

    image_id: int

    unicode_placeholder: int
    transmission_medium: str

    do_query: bool
    verbose: bool
    transfer_png: bool

    @staticmethod
    def get_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="KGP Image Display Options")
        parser.add_argument("path", type=str, help="Path to the image file", nargs="?")
        parser.add_argument("--width", type=int, default=-1, help="Number of columns to display (-1: max possible (default))")
        parser.add_argument("--height", type=int, default=-1, help="Number of rows to display (-1: max possible (default))")
        parser.add_argument("--max-cols", type=int, default=-1,
                            help="Maximum number of columns for Unicode Placeholder (-1: auto-detect (default), 0: no limit, positive integer: limit)")
        parser.add_argument("--max-rows", type=int, default=-1,
                            help="Maximum number of rows for Unicode Placeholder (-1: auto-detect (default), 0: no limit, positive integer: limit)")
        parser.add_argument("--unicode-placeholder", type=int, default=-1,
                            help="Enable Unicode Placeholder (-1: auto-detect (default), 0: disable, 1: enable)")
        parser.add_argument("--transmission-medium", type=str, default="auto",
                            help=f"Transmission medium for data (available options: {', '.join(KGP_TRANSMISSION_MEDIUM.keys())}, default: auto)")
        parser.add_argument("--image-id", type=int, default=-1, help="Image ID to use for KGP (0 to 0xFFFFFF, default: random)")
        parser.add_argument("-q", "--query", action="store_true",
                            help="Perform capability queries and quit (no image will be displayed)")
        parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
        parser.add_argument("--png", action="store_true", help="Transfer PNG data instead of raw pixel data")
        return parser

    def __init__(self, args):
        self.display_cols = args.width
        self.display_rows = args.height
        self.max_cols = args.max_cols
        self.max_rows = args.max_rows
        self.unicode_placeholder = args.unicode_placeholder
        self.image_id = args.image_id
        self.do_query = args.query
        self.verbose = args.verbose
        self.transfer_png = args.png
        # path and transmission_medium will be handled later

        try:
            self._setup_logging()

            if self.do_query:
                # handled by caller
                return

            # Validate path
            if args.path is None:
                raise ArgParseError("Image path is required unless --query or --help is specified")
            self.path = Path(args.path)
            if not self.path.is_file():
                raise ArgParseError(f"Image path does not exist or is not a file: {self.path}")

            # Validate transmission medium
            if args.transmission_medium not in KGP_TRANSMISSION_MEDIUM.keys():
                raise ArgParseError(
                    f"Invalid transmission medium: {args.transmission_medium}, available options are: {', '.join(KGP_TRANSMISSION_MEDIUM.keys())}")
            self.transmission_medium = KGP_TRANSMISSION_MEDIUM[args.transmission_medium]

            self._check_args()
            self._init_size()
            self._detect_unicode_placeholder()
            self._detect_transmission_medium()
        except ArgParseError as e:
            logging.error(f"Argument error: {e}")
            exit(1)

    def _setup_logging(self) -> None:
        if self.verbose:
            logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        else:
            logging.basicConfig(level=logging.INFO, format="%(message)s")

    def _check_args(self) -> None:
        # The specified display size should not exceed the specified maximum size
        if self.max_cols > 0 and self.max_cols < self.display_cols:
            raise ArgParseError("max-cols cannot be less than the number of display columns")
        if self.max_rows > 0 and self.max_rows < self.display_rows:
            raise ArgParseError("max-rows cannot be less than the number of display rows")

        if self.image_id < -1 or self.image_id > 0xFFFFFF:
            raise ArgParseError("Image ID must be between 0 and 0xFFFFFF (inclusive)")
        if self.image_id == -1:
            self.image_id = random_ID(0xFFFFFF)

        logging.debug(f"Image ID: {self.image_id}")

    def _init_size(self) -> None:
        if self.display_cols == 0:
            self.display_cols = -1
        if self.display_rows == 0:
            self.display_rows = -1

        size = terminal_dimensions()
        self.cell_height = size[3] // size[1]
        self.cell_width = size[2] // size[0]
        logging.debug(
            f"Terminal size: {size[0]}x{size[1]} cells, cell size: {self.cell_width}x{self.cell_height} pixels")

        # If max_cols or max_rows is not specified, use the terminal dimensions as the maximum size
        if self.max_rows < 0 or self.max_cols < 0:
            if self.max_cols < 0:
                self.max_cols = size[0]
                logging.debug(f"Auto-detected max-cols: {self.max_cols}")
            if self.max_rows < 0:
                self.max_rows = size[1]
                logging.debug(f"Auto-detected max-rows: {self.max_rows}")

    def _detect_unicode_placeholder(self) -> None:
        if self.unicode_placeholder == -1:
            self.unicode_placeholder = 1 if KGPQuery.query_unicode_placeholder_support() else 0
        elif self.unicode_placeholder not in (0, 1):
            raise ArgParseError("unicode-placeholder must be -1 (auto-detect), 0 (disable) or 1 (enable)")

        # Unicode Placeholder have a maximum size limit due to the limited number of diacritics
        if self.unicode_placeholder == 1:
            if self.display_cols > KGP_UNICODE_MAX_SIZE:
                logging.warning(
                    f"display width for Unicode Placeholder cannot exceed {KGP_UNICODE_MAX_SIZE} columns, disabling Unicode Placeholder")
                self.unicode_placeholder = 0
            elif self.display_rows > KGP_UNICODE_MAX_SIZE:
                logging.warning(
                    f"display height for Unicode Placeholder cannot exceed {KGP_UNICODE_MAX_SIZE} rows, disabling Unicode Placeholder")
                self.unicode_placeholder = 0
            elif self.max_cols > KGP_UNICODE_MAX_SIZE:
                logging.warning(
                    f"max-cols for Unicode Placeholder cannot exceed {KGP_UNICODE_MAX_SIZE}, disabling Unicode Placeholder")
                self.unicode_placeholder = 0
            elif self.max_rows > KGP_UNICODE_MAX_SIZE:
                logging.warning(
                    f"max-rows for Unicode Placeholder cannot exceed {KGP_UNICODE_MAX_SIZE}, disabling Unicode Placeholder")
                self.unicode_placeholder = 0

        logging.debug(f"Unicode Placeholder support: {'enabled' if self.unicode_placeholder else 'disabled'}")

    def _detect_transmission_medium(self) -> None:
        if self.transmission_medium == "auto":
            if KGPQuery.query_transmission_medium_support(medium="s", format="32" if not self.transfer_png else "100"):
                self.transmission_medium = "s"
            elif KGPQuery.query_transmission_medium_support(medium="t", format="32" if not self.transfer_png else "100"):
                self.transmission_medium = "t"
            elif KGPQuery.query_transmission_medium_support(medium="d", format="32" if not self.transfer_png else "100"):
                self.transmission_medium = "d"
            else:
                logging.warning("No supported transmission medium detected, defaulting to direct transmission")
                self.transmission_medium = "d"

        logging.debug(f"Transmission medium: {self.transmission_medium}")
