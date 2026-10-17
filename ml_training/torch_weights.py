"""Load a PyTorch state dict into NumPy arrays without importing torch.

Supports both the legacy (pre-1.6) serialization format and the zip format.
Used only for converting the published EfficientNet-B0 ImageNet weights
(lukemelas/EfficientNet-PyTorch release 1.0, sha256 prefix 355c32eb) to ONNX.
"""
from __future__ import annotations

import pickle
import struct
import zipfile
from collections import OrderedDict

import numpy as np

_DTYPES = {
    "FloatStorage": np.float32,
    "DoubleStorage": np.float64,
    "HalfStorage": np.float16,
    "LongStorage": np.int64,
    "IntStorage": np.int32,
    "ByteStorage": np.uint8,
}


class _StorageRef:
    def __init__(self, dtype, key, numel=None):
        self.dtype = dtype
        self.key = key
        self.numel = numel
        self.array: np.ndarray | None = None


class _StorageType:
    def __init__(self, name):
        self.name = name


def _rebuild_tensor_v2(storage, offset, size, stride, *_args):
    return ("tensor", storage, offset, tuple(size), tuple(stride))


def _rebuild_parameter(data, *_args):
    return data


class _Unpickler(pickle.Unpickler):
    def __init__(self, f, storages):
        super().__init__(f)
        self.storages = storages

    def find_class(self, module, name):
        if module == "torch._utils" and name == "_rebuild_tensor_v2":
            return _rebuild_tensor_v2
        if module == "torch._utils" and name == "_rebuild_parameter":
            return _rebuild_parameter
        if module == "torch" and name in _DTYPES:
            return _StorageType(name)
        if module == "collections" and name == "OrderedDict":
            return OrderedDict
        raise pickle.UnpicklingError(f"refusing to load {module}.{name}")

    def persistent_load(self, pid):
        # legacy: ('storage', type, key, location, numel, view_metadata)
        # zip:    ('storage', type, key, location, numel)
        _, stype, key, _loc, numel = pid[:5]
        if key not in self.storages:
            self.storages[key] = _StorageRef(_DTYPES[stype.name], key, numel)
        return self.storages[key]


def _materialise(obj):
    out = OrderedDict()
    for k, v in obj.items():
        if isinstance(v, tuple) and v and v[0] == "tensor":
            _, st, offset, size, stride = v
            base = st.array
            itemsize = base.dtype.itemsize
            arr = np.lib.stride_tricks.as_strided(
                base[offset:], shape=size, strides=tuple(s * itemsize for s in stride)
            )
            out[k] = np.array(arr, copy=True)
    return out


def load_state_dict(path: str) -> "OrderedDict[str, np.ndarray]":
    storages: dict[str, _StorageRef] = {}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            prefix = z.namelist()[0].split("/")[0]
            obj = _Unpickler(z.open(f"{prefix}/data.pkl"), storages).load()
            for key, ref in storages.items():
                ref.array = np.frombuffer(z.read(f"{prefix}/data/{key}"), dtype=ref.dtype)
        return _materialise(obj)

    with open(path, "rb") as f:
        magic = pickle.load(f)
        if magic != 0x1950A86A20F9469CFC6C:
            raise ValueError("not a torch legacy file")
        pickle.load(f)  # protocol version
        pickle.load(f)  # sys info
        obj = _Unpickler(f, storages).load()
        keys = pickle.load(f)
        for key in keys:
            ref = storages[key]
            (numel,) = struct.unpack("<q", f.read(8))
            ref.array = np.frombuffer(f.read(numel * np.dtype(ref.dtype).itemsize), dtype=ref.dtype)
    return _materialise(obj)
