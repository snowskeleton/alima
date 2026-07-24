"""Backblaze B2 storage service (S3-compatible API).

Configuration comes from Server Settings (Admin → Server Settings), falling back
to the B2_* environment variables, matching how the rest of the app resolves
settings: database value > .env > hardcoded default.
"""

import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import monotonic

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ..utils.settings_cache import get_cached_setting

logger = logging.getLogger(__name__)


class B2StorageService:
    """Wraps boto3 for Backblaze B2 S3-compatible storage."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        signed_url_ttl: int = 3600,
        max_pool_connections: int = 50,
        existence_cache_ttl: int = 300,
    ):
        self._bucket = bucket
        self._signed_url_ttl = signed_url_ttl
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            # Default pool is 10. A podcast player prefetching a large feed fires
            # many concurrent serves, each doing one head_object; a small pool
            # thrashes ("connection pool is full, discarding connection").
            config=Config(
                signature_version="s3v4",
                max_pool_connections=max_pool_connections,
            ),
        )
        # Short-lived existence cache. Most keys exist, and the same feed's
        # episodes get requested repeatedly; without this every serve is a B2
        # round-trip. Only positive ("present") results are cached — a missing
        # key gets cleared off the book row by the caller, so it won't be asked
        # about again, and caching a false negative could pin a just-uploaded
        # file as absent.
        self._existence_cache_ttl = existence_cache_ttl
        self._present_until: dict[str, float] = {}
        self._cache_lock = Lock()

    def upload_file(self, local_path: Path, key: str, content_type: str | None = None) -> None:
        """
        Upload a local file to B2.

        Pass content_type for audio. boto3's upload_file does NOT sniff it, so
        without this S3 stores "binary/octet-stream" and podcast players refuse
        the episode.
        """
        logger.info(f"Uploading {local_path} to B2 key {key!r}")
        extra = {"ContentType": content_type} if content_type else None
        self._client.upload_file(str(local_path), self._bucket, key, ExtraArgs=extra)
        with self._cache_lock:
            self._present_until[key] = monotonic() + self._existence_cache_ttl
        logger.info(f"Upload complete: {key}")

    def get_signed_url(self, key: str, content_type: str | None = None) -> str:
        """
        Generate a presigned GET URL expiring after the configured TTL.

        content_type is served back via ResponseContentType, which overrides
        whatever is stored on the object. That deliberately also repairs files
        uploaded before upload_file started setting ContentType — no re-upload
        of anyone's existing library needed.
        """
        params = {"Bucket": self._bucket, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        return self._client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=self._signed_url_ttl,
        )

    def file_exists(self, key: str) -> bool:
        """
        Whether the bucket actually holds this key.

        Raises on anything other than a clean "not found" — a credential or
        network failure must NOT be reported as a missing object, or callers
        would treat an outage as proof the file is gone and discard good keys.

        A positive result is cached for existence_cache_ttl seconds so a feed of
        hundreds of books doesn't head_object the same objects on every serve.
        """
        now = monotonic()
        with self._cache_lock:
            expiry = self._present_until.get(key)
            if expiry is not None and expiry > now:
                return True

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            if e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise

        with self._cache_lock:
            self._present_until[key] = now + self._existence_cache_ttl
        return True

    def delete_file(self, key: str) -> None:
        """Delete a file from B2."""
        with self._cache_lock:
            self._present_until.pop(key, None)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            logger.info(f"Deleted B2 key {key!r}")
        except Exception as e:
            logger.warning(f"Failed to delete B2 key {key!r}: {e}")

    def test_connection(self) -> None:
        """
        Verify the bucket is reachable with the configured credentials.

        Raises the underlying botocore exception on failure so the caller can
        surface a useful message.
        """
        self._client.head_bucket(Bucket=self._bucket)


def normalise_endpoint(value: str | None) -> str | None:
    """
    Clean up a pasted B2 endpoint.

    Backblaze shows the endpoint without a scheme ("s3.us-west-002.backblazeb2.com")
    and copy-paste routinely brings whitespace along, but boto3 demands a full
    URL and raises ValueError otherwise.
    """
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    if "://" not in value:
        value = f"https://{value}"

    return value.rstrip("/")


@lru_cache(maxsize=4)
def _build_service(
    bucket: str,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    signed_url_ttl: int,
    max_pool_connections: int,
    existence_cache_ttl: int,
) -> B2StorageService:
    """
    Cache the boto3 client per distinct credential set.

    Building a client resolves credentials and endpoints, which is too expensive
    to repeat on every file request. Keying the cache on the config values means
    changing credentials in the GUI naturally yields a new client — there is no
    separate invalidation to remember. (The settings themselves are cached by
    get_cached_setting, which the settings router clears on save.)
    """
    return B2StorageService(
        bucket,
        endpoint_url,
        access_key_id,
        secret_access_key,
        signed_url_ttl,
        max_pool_connections,
        existence_cache_ttl,
    )


def get_storage_service() -> B2StorageService | None:
    """
    Return a B2StorageService if B2 is configured and enabled, else None.

    Never raises. This is called on every file request and on every scheduler
    tick, so a malformed setting must degrade to "B2 off" (serve locally) rather
    than take file serving down with it.
    """
    try:
        if not get_cached_setting("b2_enabled", False, bool):
            return None

        bucket = (get_cached_setting("b2_bucket_name", None, str) or "").strip()
        endpoint_url = normalise_endpoint(get_cached_setting("b2_endpoint_url", None, str))
        access_key_id = (get_cached_setting("b2_access_key_id", None, str) or "").strip()
        secret_access_key = (get_cached_setting("b2_secret_access_key", None, str) or "").strip()

        if not all([bucket, endpoint_url, access_key_id, secret_access_key]):
            logger.warning("B2 is enabled but its configuration is incomplete; serving files locally")
            return None

        ttl = get_cached_setting("b2_signed_url_ttl_seconds", 3600, int)
        max_pool = get_cached_setting("b2_max_pool_connections", 50, int)
        existence_ttl = get_cached_setting("b2_existence_cache_ttl_seconds", 300, int)

        return _build_service(
            bucket,
            endpoint_url,
            access_key_id,
            secret_access_key,
            ttl,
            max_pool,
            existence_ttl,
        )

    except Exception as e:
        logger.error(
            f"B2 is enabled but its configuration is invalid ({e}); serving files locally. "
            f"Check Admin → Server Settings → Storage."
        )
        return None
