import logging
from PIL import Image
from io import BytesIO

from .utils import smart_resize
from .cli_options import KGPOptions
from .medium import KGPMedium, KGPMediumCreationError


class KGPEncoderBase:
    image_id: int
    # Original image
    image: Image.Image
    # Resized image that fits the terminal dimensions
    resized_image: Image.Image
    # Medium
    medium_mgr: KGPMedium

    # Displayed image dimensions in terms of character cells
    display_cols: int
    display_rows: int

    transfer_png: bool

    def __init__(self, options: KGPOptions):
        self.image_id = options.image_id
        self.transfer_png = options.transfer_png
        self._init_image(options)
        self._init_size(options)
        self._init_medium(options)

    def _init_image(self, options: KGPOptions) -> None:
        """Load the image and convert it to a supported pixel format"""
        image = Image.open(options.path).convert("RGB")
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            self.image = image.convert("RGBA")
            logging.debug("Image has alpha channel, using RGBA format")
        else:
            self.image = image.convert("RGB")
            logging.debug("Image does not have alpha channel, using RGB format")

    def _init_size(self, options: KGPOptions) -> None:
        """Initialize size-related attributes based on the image and terminal dimensions"""
        self.resized_image = smart_resize(self.image,
                                          display_cols=options.display_cols,
                                          display_rows=options.display_rows,
                                          cell_width=options.cell_width,
                                          cell_height=options.cell_height,
                                          max_cols=options.max_cols,
                                          max_rows=options.max_rows)
        self.display_cols = int(self.resized_image.width / options.cell_width)
        self.display_rows = int(self.resized_image.height / options.cell_height)
        logging.debug(f"Resized image to {self.resized_image.width}x{self.resized_image.height} pixels, "
                      f"display size: {self.display_cols}x{self.display_rows} cells")

    def _init_medium(self, options: KGPOptions) -> None:
        """Initialize the transmission medium for the image data"""
        data = b""
        if self.transfer_png:
            buf = BytesIO()
            self.image.save(buf, format="PNG")
            data = buf.getvalue()
        else:
            data = self.resized_image.tobytes()

        try:
            self.medium_mgr = KGPMedium.create(
                image_id=self.image_id, data=data, medium=options.transmission_medium)
        except KGPMediumCreationError as e:
            logging.warning(f"Failed to initialize transmission medium: {e}. Retrying with direct transmission.")
            try:
                self.medium_mgr = KGPMedium.create(
                    image_id=self.image_id, data=data, medium="d")
            except KGPMediumCreationError as e:
                raise RuntimeError("Failed to initialize transmission medium") from e

    def _format_KGP(self, payload: str, options_str: str, chunk_size: int) -> list[str]:
        """Format the KGP payload into one or more escape sequences based on the chunk size"""
        if len(payload) <= chunk_size:
            return [f"\033_G{options_str};{payload}\033\\"]
        else:
            ret = [f"\033_G{options_str},m=1;{payload[:chunk_size]}\033\\"]
            for offset in range(chunk_size, len(payload), chunk_size):
                chunk = payload[offset:offset + chunk_size]
                # m=0 for the last chunk, m=1 for all previous
                m = 1 if offset + chunk_size < len(payload) else 0
                # The other options only need to be specified in the first chunk, subsequent chunks can omit them
                ret.append(f"\033_Gm={m};{chunk}\033\\")
            return ret

    def _gen_options(self) -> str:
        """Generate the options string for the KGP escape sequence"""
        # format = "32" if self.image.mode == "RGBA" else "24"
        format = ""
        if self.transfer_png:
            format = "100"
        else:
            format = "32" if self.image.mode == "RGBA" else "24"

        # a=T: Action, transmit and display
        # f=...: Pixel format, 24 for RGB, 32 for RGBA, 100 for PNG
        # t=...: transmission medium, d for transmitting data directly in control sequence, s for shared memory
        # c=...,r=...: Specify the image dimensions in terms of character cells
        # s=...,v=...: Specify the image dimensions in pixels, required when transmitting raw pixel data
        # o=z: Enable zlib compression (optional)
        options = f"i={self.image_id},a=T,f={format},t={self.medium_mgr.medium_identifier()},q=2,"\
            f"c={self.display_cols},r={self.display_rows},"\
            f"s={self.resized_image.width},v={self.resized_image.height}"
        if self.medium_mgr.do_compression():
            options += ",o=z"
        return options

    def construct_KGP(self, chunk_size: int = 4096) -> list[str]:
        """Construct the KGP escape sequences for the image"""
        if chunk_size <= 0:
            raise ValueError("Chunk size must be a positive integer.")

        options = self._gen_options()
        payload = self.medium_mgr.construct_payload()
        ret = self._format_KGP(payload, options, chunk_size)
        return ret

    def delete_image(self) -> str:
        """Construct the escape sequence to delete the image from the terminal, also cleanup the medium if necessary"""
        self.medium_mgr.cleanup()
        return f"\033_Ga=d,d=i,i={self.image_id}\033\\"
