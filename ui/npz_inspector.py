"""Read only bounded NPY headers for GUI selection, never array payloads."""

from pathlib import Path
from io import BytesIO
import struct
from zipfile import ZipFile

import numpy as np


def describe_npz(path):
    path = Path(path)
    if path.stat().st_size > 258 * 1024**2:
        raise ValueError("NPZ archive exceeds the inspection budget")
    result = {}
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 256 or sum(m.file_size for m in members) > 256 * 1024**2:
            raise ValueError("NPZ array budget exceeded")
        if len({m.filename for m in members}) != len(members):
            raise ValueError("Duplicate NPZ entries")
        for member in members:
            if (
                not member.filename.endswith(".npy")
                or "/" in member.filename
                or "\\" in member.filename
            ):
                raise ValueError("Invalid NPZ array entry")
            with archive.open(member) as stream:
                version = np.lib.format.read_magic(stream)
                if version not in ((1, 0), (2, 0)):
                    raise ValueError("Unsupported NPY header version")
                length_bytes = stream.read(2 if version == (1, 0) else 4)
                if len(length_bytes) != (2 if version == (1, 0) else 4):
                    raise ValueError("Truncated NPY header length")
                length = struct.unpack(
                    "<H" if version == (1, 0) else "<I", length_bytes
                )[0]
                if length > 10000:
                    raise ValueError("NPY header exceeds the inspection budget")
                header = stream.read(length)
                if len(header) != length:
                    raise ValueError("Truncated NPY header")
                bounded = BytesIO(length_bytes + header)
                if version == (1, 0):
                    shape, order, dtype = np.lib.format.read_array_header_1_0(
                        bounded, max_header_size=10000
                    )
                elif version == (2, 0):
                    shape, order, dtype = np.lib.format.read_array_header_2_0(
                        bounded, max_header_size=10000
                    )
                else:
                    raise ValueError("Unsupported NPY header version")
            if (
                dtype.hasobject
                or len(shape) > 8
                or any(dimension < 0 for dimension in shape)
            ):
                raise ValueError(
                    "Object arrays or excessive dimensions are not allowed"
                )
            size = int(dtype.itemsize)
            for dimension in shape:
                size *= int(dimension)
            if size > 256 * 1024**2:
                raise ValueError("Declared array exceeds the inspection budget")
            result[member.filename[:-4]] = {
                "shape": tuple(shape),
                "dtype": str(dtype),
                "order": "F" if order else "C",
            }
    return result
