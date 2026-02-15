import re
import os
import sys
import termios
import logging
from select import select
import time

from .utils import NoInteractiveTerminalError, atty_fd, random_ID, mock_png_data
from .medium import KGPMedium


class KGPQuery():
    @staticmethod
    def _do_query(code: str, expected_response: re.Pattern, fence_response: re.Pattern, timeout: float = -1) -> bool:
        """Helper function to send a query and wait for the expected response"""
        if timeout < 0:
            timeout = 1 if os.environ.get("SSH_TTY") else 0.1

        try:
            fd = atty_fd()
        except NoInteractiveTerminalError as e:
            logging.warning(f"Cannot perform query: {e}")
            return False

        old_settings = termios.tcgetattr(fd)
        response = ""

        try:
            new_settings = termios.tcgetattr(fd)
            # Disable canonical mode and echo
            new_settings[3] = new_settings[3] & ~termios.ICANON & ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, new_settings)

            sys.stdout.write(code)
            sys.stdout.flush()

            success = False
            while True:
                # Set a timeout to prevent blocking indefinitely
                r, w, e = select([fd], [], [], timeout)
                if not r:
                    break

                char = os.read(fd, 1)
                if not char:
                    break

                response += char.decode('ascii', errors='ignore')

                if expected_response.search(response):
                    success = True

                if fence_response.search(response):
                    break

            logging.debug(f"Received response: {response.encode('unicode_escape')}")

            return success
        except Exception:
            logging.warning("Exception occurred while querying terminal support", exc_info=True)
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)

        return False

    @staticmethod
    def _mock_data(format: str, width: int = 1, height: int = 1) -> bytes:
        if format == "32":
            return b"\x00\x00\x00\x00" * (width * height)
        elif format == "24":
            return b"\x00\x00\x00" * (width * height)
        elif format == "100":
            return mock_png_data(width, height)
        else:
            raise ValueError(f"Unsupported format: {format}")

    @staticmethod
    def query_support() -> bool:
        return KGPQuery.query_transmission_medium_support(medium="d", format="24")

    @staticmethod
    def query_unicode_placeholder_support() -> bool:
        if os.environ.get("KITTY_PID") or os.environ.get("GHOSTTY_SHELL_FEATURES"):
            return KGPQuery.query_support()
        return False

    @staticmethod
    def query_transmission_medium_support(medium: str = "d", format: str = "32") -> bool:
        kgp_medium = None
        try:
            mock_width = 1
            mock_height = 1
            kgp_medium = KGPMedium.create(medium=medium,
                                          image_id=random_ID(0xFFFFFF),
                                          data=KGPQuery._mock_data(format, mock_width, mock_height))
            query_code = f"\033_Gs={mock_width},v={mock_height},a=q,f={format}{kgp_medium.medium_options()};{kgp_medium.construct_payload()}\033\\"
            expected_response = re.compile(rf"\033_Gi={kgp_medium.image_id};OK\033\\")
            fence_code = "\033[c"
            fence_response = re.compile(r"\033\[\?[0-9;]*c")
            return KGPQuery._do_query(query_code + fence_code, expected_response, fence_response)
        except Exception as e:
            logging.warning(f"Exception occurred while querying transmission medium support: {e}")
            return False
        finally:
            if kgp_medium is not None:
                kgp_medium.cleanup()

    @staticmethod
    def query_all() -> dict[str, bool]:
        ret = {}

        support_unicode_placeholders = KGPQuery.query_unicode_placeholder_support()
        support_direct_32 = KGPQuery.query_transmission_medium_support(medium="d", format="32")
        support_direct_24 = KGPQuery.query_transmission_medium_support(medium="d", format="24")
        support_direct_png = KGPQuery.query_transmission_medium_support(medium="d", format="100")

        support_shared_memory_32 = KGPQuery.query_transmission_medium_support(medium="s", format="32")
        support_shared_memory_24 = KGPQuery.query_transmission_medium_support(medium="s", format="24")
        support_shared_memory_png = KGPQuery.query_transmission_medium_support(medium="s", format="100")

        support_temp_file_32 = KGPQuery.query_transmission_medium_support(medium="t", format="32")
        support_temp_file_24 = KGPQuery.query_transmission_medium_support(medium="t", format="24")
        support_temp_file_png = KGPQuery.query_transmission_medium_support(medium="t", format="100")

        support_file_32 = KGPQuery.query_transmission_medium_support(medium="f", format="32")
        support_file_24 = KGPQuery.query_transmission_medium_support(medium="f", format="24")
        support_file_png = KGPQuery.query_transmission_medium_support(medium="f", format="100")

        ret["Unicode Placeholders"] = support_unicode_placeholders
        ret["Direct Transmission (32bit)"] = support_direct_32
        ret["Direct Transmission (24bit)"] = support_direct_24
        ret["Direct Transmission (PNG)"] = support_direct_png
        ret["Shared Memory Transmission (32bit)"] = support_shared_memory_32
        ret["Shared Memory Transmission (24bit)"] = support_shared_memory_24
        ret["Shared Memory Transmission (PNG)"] = support_shared_memory_png
        ret["Temporary File Transmission (32bit)"] = support_temp_file_32
        ret["Temporary File Transmission (24bit)"] = support_temp_file_24
        ret["Temporary File Transmission (PNG)"] = support_temp_file_png
        ret["File Transmission (32bit)"] = support_file_32
        ret["File Transmission (24bit)"] = support_file_24
        ret["File Transmission (PNG)"] = support_file_png
        return ret
