from .encoder import KGPEncoderBase
from .utils import random_ID
from .constants import KGP_PLACEHOLDER, KGP_DIACRITICS


class KGPEncoderUnicode(KGPEncoderBase):
    def _init_id(self):
        """Initialize a smaller random image ID"""
        self.image_id = random_ID(0xFFFFFF)

    def _gen_options(self) -> str:
        """Generate the options string for the KGP escape sequence"""
        options = super()._gen_options()
        # U=1: Enable Unicode Placeholders
        options += ",U=1"
        return options

    def construct_unicode_placeholders(self) -> list[str]:
        """Construct the Unicode placeholders for the image"""
        # Using 24-bit True Color foreground to encode the image ID,
        # the maximum id is therefore 0xFFFFFF, which is likely enough
        image_id_str = f"\033[38;2;{(self.image_id >> 16) & 0xFF};{(self.image_id >> 8) & 0xFF};{self.image_id & 0xFF}m"
        ret = []
        for i in range(self.display_rows):
            line = image_id_str

            # Placehoder + Row Diacritic + Column Diacritic
            line += f"{KGP_PLACEHOLDER}{KGP_DIACRITICS[i]}{KGP_DIACRITICS[0]}"
            for _ in range(1, self.display_cols):
                # Col index and row index will be automatically determined
                line += KGP_PLACEHOLDER

            line += "\033[39m"
            ret.append(line)

        return ret
