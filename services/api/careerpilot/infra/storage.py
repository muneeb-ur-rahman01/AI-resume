"""DocumentStorageProvider: private object storage for uploaded/generated files.

- `local`: filesystem directory (development/tests). Downloads are streamed through the API after an
  ownership check, so no public URL exists.
- `s3`: any S3-compatible store (AWS S3, MinIO). Objects are private; downloads use short-lived
  presigned URLs generated after the API's authorization check.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Protocol

from careerpilot.config import get_settings
from careerpilot.errors import ServiceUnavailable


class StorageProvider(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str) -> str | None: ...


def new_object_key(prefix: str) -> str:
    """Random, non-guessable key. Never derived from user input."""
    return f"{prefix}/{secrets.token_hex(4)}/{secrets.token_urlsafe(24)}"


class LocalStorageProvider:
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise ServiceUnavailable("Stored file is unavailable.") from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def signed_url(self, key: str, filename: str) -> str | None:
        return None  # served through the authenticated API instead


class S3StorageProvider:
    name = "s3"

    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key.get_secret_value() if s.s3_secret_access_key else None,
        )
        self.ttl = s.signed_url_ttl_seconds

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
            )
        except Exception as exc:
            raise ServiceUnavailable("File storage is temporarily unavailable.") from exc

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise ServiceUnavailable("File storage is temporarily unavailable.") from exc

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key: str, filename: str) -> str | None:
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")[:100] or "document"
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{safe_name}"',
            },
            ExpiresIn=self.ttl,
        )


_storage: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3StorageProvider() if s.storage_provider == "s3" else LocalStorageProvider(s.local_storage_path)
    return _storage


def set_storage(provider: StorageProvider | None) -> None:
    global _storage
    _storage = provider
