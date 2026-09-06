"""
File storage abstraction layer supporting both local filesystem (dev/local) 
and S3-compatible object storage (production).

This module provides a unified interface for file operations while
allowing the underlying storage backend to be swapped via environment variables.

Usage:
    from app.core.storage import get_storage, FileStorage
    
    storage = get_storage()
    storage.save_file("resumes/user123.pdf", file_data)
    url = storage.get_presigned_url("resumes/user123.pdf", expiry=3600)
"""
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.paths import get_app_data_dir


class FileStorage(ABC):
    """Abstract base class for file storage backends."""
    
    @abstractmethod
    def save_file(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """Save a file to storage."""
        pass
    
    @abstractmethod
    def read_file(self, key: str) -> bytes:
        """Read a file from storage."""
        pass
    
    @abstractmethod
    def file_exists(self, key: str) -> bool:
        """Check if a file exists in storage."""
        pass
    
    @abstractmethod
    def delete_file(self, key: str) -> bool:
        """Delete a file from storage. Returns True if deleted, False if not found."""
        pass
    
    @abstractmethod
    def get_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """Generate a presigned URL for temporary access to a file."""
        pass
    
    @abstractmethod
    def get_file_path(self, key: str) -> Optional[Path]:
        """Get local filesystem path for a file (only for local storage)."""
        pass


class LocalFileStorage(FileStorage):
    """Local filesystem storage implementation."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or get_app_data_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _resolve_path(self, key: str) -> Path:
        """Resolve a storage key to a local filesystem path."""
        # Prevent path traversal
        key = key.lstrip("/")
        if ".." in key or key.startswith("/"):
            raise ValueError(f"Invalid key: {key}")
        return (self.base_dir / key).resolve()
    
    def save_file(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    
    def read_file(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return path.read_bytes()
    
    def file_exists(self, key: str) -> bool:
        try:
            path = self._resolve_path(key)
            return path.exists()
        except ValueError:
            return False
    
    def delete_file(self, key: str) -> bool:
        try:
            path = self._resolve_path(key)
            if path.exists():
                path.unlink()
                return True
            return False
        except ValueError:
            return False
    
    def get_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """For local storage, return a signed media URL that will be validated by the media endpoint."""
        from app.core.tokens import create_media_token
        sig, exp = create_media_token(key, expiry)
        # Return the internal media endpoint URL with signature
        return f"/media/{key}?sig={sig}&exp={exp}"
    
    def get_file_path(self, key: str) -> Optional[Path]:
        """Get the local filesystem path for a file."""
        try:
            path = self._resolve_path(key)
            return path if path.exists() else None
        except ValueError:
            return None


class S3FileStorage(FileStorage):
    """S3-compatible object storage implementation."""
    
    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        prefix: str = "",
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        
        # Configure boto3 client
        config = Config(
            region_name=region,
            retries={"max_attempts": 3},
        )
        
        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=config,
        )
        
        # Verify bucket exists/accessible
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError as e:
            raise RuntimeError(f"Cannot access S3 bucket '{bucket}': {e}")
    
    def _make_key(self, key: str) -> str:
        """Prefix the key with the configured prefix."""
        key = key.lstrip("/")
        return f"{self.prefix}{key}"
    
    def save_file(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        s3_key = self._make_key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
        )
    
    def read_file(self, key: str) -> bytes:
        s3_key = self._make_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=s3_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {key}")
            raise
    
    def file_exists(self, key: str) -> bool:
        s3_key = self._make_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
    
    def delete_file(self, key: str) -> bool:
        s3_key = self._make_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
    
    def get_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """Generate a presigned URL for temporary access to an S3 object."""
        s3_key = self._make_key(key)
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": s3_key},
                ExpiresIn=expiry,
            )
            return url
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")
    
    def get_file_path(self, key: str) -> Optional[Path]:
        """S3 storage doesn't have local paths."""
        return None


# Global storage instance
_storage: Optional[FileStorage] = None


def get_storage() -> FileStorage:
    """Get the global storage instance, creating it if needed."""
    global _storage
    if _storage is None:
        _storage = _create_storage()
    return _storage


def set_storage(storage: FileStorage) -> None:
    """Set the global storage instance (for testing)."""
    global _storage
    _storage = storage


def _create_storage() -> FileStorage:
    """Create storage backend based on environment configuration."""
    storage_backend = os.environ.get("STORAGE_BACKEND", "local").lower()
    
    if storage_backend == "s3":
        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise ValueError("S3_BUCKET environment variable is required for S3 storage")
        
        return S3FileStorage(
            bucket=bucket,
            region=os.environ.get("S3_REGION", "us-east-1"),
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            access_key_id=os.environ.get("S3_ACCESS_KEY_ID") or None,
            secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY") or None,
            prefix=os.environ.get("S3_PREFIX", ""),
        )
    else:
        return LocalFileStorage()