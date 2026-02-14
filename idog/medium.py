import os
from multiprocessing import shared_memory
from abc import ABC, abstractmethod
import tempfile

from .utils import base64_encode, zlib_compress


class KGPMediumCreationError(Exception):
    pass


class KGPMedium(ABC):
    image_id: int

    @abstractmethod
    def __init__(self, image_id: int, data: bytes) -> None:
        self.image_id = image_id

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def construct_payload(self) -> str:
        pass

    @abstractmethod
    def medium_identifier(self) -> str:
        pass

    @abstractmethod
    def do_compression(self) -> bool:
        pass

    @staticmethod
    def create(image_id: int, data: bytes, medium: str) -> "KGPMedium":
        if medium == "d":
            return KGPMediumDirect(image_id, data)
        elif medium == "s":
            return KGPMediumSharedMemory(image_id, data)
        elif medium == "t":
            return KGPMediumTempFile(image_id, data)
        else:
            raise KGPMediumCreationError(f"Unsupported transmission medium: {medium}")


class KGPMediumDirect(KGPMedium):
    payload: str

    def __init__(self, image_id: int, data: bytes) -> None:
        super().__init__(image_id, data)
        self.payload = base64_encode(zlib_compress(data))

    def cleanup(self):
        pass

    def construct_payload(self) -> str:
        return self.payload

    def medium_identifier(self) -> str:
        return "d"

    def do_compression(self) -> bool:
        return True


class KGPMediumSharedMemory(KGPMedium):
    shm_name: str
    shm: shared_memory.SharedMemory | None

    def _construct_memory_name(self) -> str:
        return f"idog_{self.image_id}"

    def __init__(self, image_id: int, data: bytes) -> None:
        super().__init__(image_id, data)
        self.shm_name = self._construct_memory_name()
        data_len = len(data)

        for _ in range(2):
            try:
                self.shm = shared_memory.SharedMemory(name=self.shm_name, create=True, size=data_len, track=False)
                if self.shm.buf is None:
                    raise KGPMediumCreationError("Failed to create shared memory segment")
                self.shm.buf[:data_len] = data
                break
            except FileExistsError:
                try:
                    existing_shm = shared_memory.SharedMemory(name=self.shm_name, create=False, track=False)
                except FileNotFoundError:
                    continue

                if existing_shm.size < data_len:
                    try:
                        existing_shm.close()
                        existing_shm.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                self.shm = existing_shm
                if self.shm.buf is None:
                    try:
                        existing_shm.close()
                        existing_shm.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                self.shm.buf[:data_len] = data
                break
        else:
            raise KGPMediumCreationError(f"Could not initialize SharedMemory.")

        self.image_id = image_id

    def cleanup(self):
        if self.shm is not None:
            try:
                self.shm.close()
                self.shm.unlink()
            except Exception:
                pass

    def construct_payload(self) -> str:
        return base64_encode(self.shm_name.encode("utf-8"))

    def medium_identifier(self) -> str:
        return "s"

    def do_compression(self) -> bool:
        return False


class KGPMediumTempFile(KGPMedium):
    file_path: str

    def _construct_file_path(self) -> str:
        return tempfile.mkstemp(prefix="idog_")[1]

    def __init__(self, image_id: int, data: bytes) -> None:
        super().__init__(image_id, data)
        self.file_path = self._construct_file_path()
        with open(self.file_path, "wb") as f:
            f.write(data)

    def cleanup(self):
        try:
            os.remove(self.file_path)
        except Exception:
            pass

    def construct_payload(self) -> str:
        return base64_encode(self.file_path.encode("utf-8"))

    def medium_identifier(self) -> str:
        return "t"

    def do_compression(self) -> bool:
        return False
