"""The B2 existence cache and connection-pool sizing added to stop pool thrash."""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.services.storage import B2StorageService


def make_service(existence_cache_ttl=300):
    """A service whose boto3 client is a mock — no network, no real creds."""
    svc = B2StorageService.__new__(B2StorageService)
    svc._bucket = "bucket"
    svc._signed_url_ttl = 3600
    svc._existence_cache_ttl = existence_cache_ttl
    svc._present_until = {}
    from threading import Lock
    svc._cache_lock = Lock()
    svc._client = MagicMock()
    return svc


def not_found():
    return ClientError({"ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")


def test_present_key_is_only_checked_once(monkeypatch):
    svc = make_service()
    assert svc.file_exists("k") is True
    assert svc.file_exists("k") is True
    assert svc._client.head_object.call_count == 1  # second served from cache


def test_missing_key_is_not_cached(monkeypatch):
    svc = make_service()
    svc._client.head_object.side_effect = not_found()
    assert svc.file_exists("k") is False
    assert svc.file_exists("k") is False
    assert svc._client.head_object.call_count == 2  # re-checked, never cached


def test_expired_cache_rechecks(monkeypatch):
    svc = make_service()
    t = [1000.0]
    monkeypatch.setattr("app.services.storage.monotonic", lambda: t[0])
    assert svc.file_exists("k") is True
    t[0] += 301  # past the 300s ttl
    assert svc.file_exists("k") is True
    assert svc._client.head_object.call_count == 2


def test_upload_primes_the_cache(monkeypatch, tmp_path):
    svc = make_service()
    f = tmp_path / "a.m4a"
    f.write_bytes(b"x")
    svc.upload_file(f, "k", content_type="audio/mp4")
    assert svc.file_exists("k") is True
    svc._client.head_object.assert_not_called()  # upload already proved presence


def test_delete_evicts_the_cache(monkeypatch):
    svc = make_service()
    assert svc.file_exists("k") is True          # cached present
    svc.delete_file("k")
    svc._client.head_object.side_effect = not_found()
    assert svc.file_exists("k") is False         # not served stale-present
    assert svc._client.head_object.call_count == 2


def test_non_404_error_propagates_and_is_not_cached():
    svc = make_service()
    svc._client.head_object.side_effect = ClientError(
        {"ResponseMetadata": {"HTTPStatusCode": 500}}, "HeadObject"
    )
    with pytest.raises(ClientError):
        svc.file_exists("k")
    assert "k" not in svc._present_until
