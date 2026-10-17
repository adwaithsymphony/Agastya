"""Private object storage for uploaded images.

`local` stores files under LOCAL_STORAGE_DIR (outside any public/static directory) and is intended
for development. `s3` stores objects in an S3-compatible bucket (requires boto3; credentials come
from the standard AWS environment variables). Files are only ever served through authorised API
endpoints; keys are server-generated, so user-supplied filenames never touch the filesystem.
"""
from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

_KEY_RE = re.compile(r"^[a-z0-9/_\-.]{8,200}$")


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def healthy(self) -> bool: ...


def new_key(prefix: str, ext: str) -> str:
    return f"{prefix}/{secrets.token_hex(16)}.{ext}"


def _check_key(key: str) -> str:
    if not _KEY_RE.match(key) or ".." in key or key.startswith("/"):
        raise ValueError("invalid storage key")
    return key


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / _check_key(key)).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def healthy(self) -> bool:
        try:
            probe = self.root / ".probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False


class S3Storage:  # pragma: no cover - requires external service
    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None):
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None, region_name=region or None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=_check_key(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=_check_key(key))["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_check_key(key))

    def healthy(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _storage = S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
        else:
            _storage = LocalStorage(s.local_storage_dir)
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage
