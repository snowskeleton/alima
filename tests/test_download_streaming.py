"""
Tests for streaming file downloads.

The download used to buffer the whole response in memory before writing it,
which put a gigabyte-plus audiobook (twice over, counting httpx's own buffer)
into a gunicorn worker's heap and got it OOM-killed. These tests pin the
streaming behaviour and the progress reporting that rides along with it.
"""

import types

import httpx
import pytest

from app.services.book_download import BookDownloadService


class _FakeStream:
    """Stands in for httpx.stream()'s context manager."""

    def __init__(self, chunks, status_code=200, headers=None):
        self._chunks = chunks
        self.status_code = status_code
        self.headers = headers if headers is not None else {}
        self.content_accessed = False
        self._text = ""

    @property
    def content(self):
        # Touching this on a streamed response is the bug we're guarding
        # against: it pulls the entire body into memory.
        self.content_accessed = True
        return b"".join(self._chunks)

    @property
    def text(self):
        return self._text

    def read(self):
        return self.content

    def iter_bytes(self, chunk_size=None):
        yield from self._chunks

    def raise_for_status(self):
        if self.status_code != 200:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "https://example.test/f"),
                response=httpx.Response(self.status_code),
            )

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def service():
    return BookDownloadService(db=None)


def _patch_stream(monkeypatch, fake):
    def _stream(method, url, **kwargs):
        _stream.kwargs = kwargs
        return fake

    monkeypatch.setattr(httpx, "stream", _stream)
    return _stream


def test_body_is_written_without_buffering(monkeypatch, tmp_path, service):
    chunks = [b"a" * 1024, b"b" * 1024, b"c" * 512]
    fake = _FakeStream(chunks, headers={"Content-Length": "2560"})
    _patch_stream(monkeypatch, fake)

    out = tmp_path / "book.aaxc"
    service._download_file("https://cloudfront.net/book.aaxc", out)

    assert out.read_bytes() == b"".join(chunks)
    assert fake.content_accessed is False, "response.content buffers the whole body"


def test_progress_callback_reports_cumulative_bytes(monkeypatch, tmp_path, service):
    chunks = [b"x" * 100, b"y" * 200, b"z" * 300]
    _patch_stream(monkeypatch, _FakeStream(chunks, headers={"Content-Length": "600"}))

    seen = []
    out = tmp_path / "book.aaxc"
    service._download_file(
        "https://cloudfront.net/book.aaxc",
        out,
        progress_callback=lambda written, total: seen.append((written, total)),
    )

    assert seen == [(100, 600), (300, 600), (600, 600)]


def test_missing_content_length_reports_none_total(monkeypatch, tmp_path, service):
    _patch_stream(monkeypatch, _FakeStream([b"x" * 50]))

    seen = []
    service._download_file(
        "https://cloudfront.net/book.aaxc",
        tmp_path / "book.aaxc",
        progress_callback=lambda written, total: seen.append((written, total)),
    )

    assert seen == [(50, None)]


def test_download_without_callback_still_works(monkeypatch, tmp_path, service):
    """Covers the cover-art path, which has no progress to report."""
    _patch_stream(monkeypatch, _FakeStream([b"jpegdata"]))

    out = tmp_path / "cover.jpg"
    service._download_file("https://cloudfront.net/cover.jpg", out)

    assert out.read_bytes() == b"jpegdata"


def test_error_status_raises(monkeypatch, tmp_path, service):
    _patch_stream(monkeypatch, _FakeStream([b""], status_code=403))

    with pytest.raises(httpx.HTTPStatusError):
        service._download_file("https://cloudfront.net/book.aaxc", tmp_path / "book.aaxc")


def test_timeout_is_set(monkeypatch, tmp_path, service):
    """A hung CDN connection should surface, not wedge a worker forever."""
    stream = _patch_stream(monkeypatch, _FakeStream([b"x"]))

    service._download_file("https://cloudfront.net/book.aaxc", tmp_path / "book.aaxc")

    assert stream.kwargs.get("timeout") is not None


def test_authenticated_path_streams(monkeypatch, tmp_path, service):
    """
    The audible client's raw_request(stream=True) returns a context manager
    wrapping httpx's own stream(), so it drives the same loop.
    """
    fake = _FakeStream([b"authed" * 10], headers={"Content-Length": "60"})
    calls = {}

    class _Client:
        def raw_request(self, method, url, **kwargs):
            calls.update(kwargs)
            return fake

    out = tmp_path / "book.aaxc"
    service._download_file("https://api.audible.com/book", out, audible_client=_Client())

    assert calls["stream"] is True
    assert calls["apply_auth_flow"] is True
    assert out.read_bytes() == b"authed" * 10
    assert fake.content_accessed is False


class TestDecryptProgress:
    """
    Decryption reports progress through snowcrypt's callback when the installed
    version has one, and falls back to watching the output file grow when it
    doesn't. Both paths must report; only the fidelity differs.
    """

    def test_uses_snowcrypt_callback_when_available(self, monkeypatch, tmp_path, service):
        import app.services.book_download as bd

        monkeypatch.setattr(bd, "_SNOWCRYPT_REPORTS_PROGRESS", True)

        seen = []

        def fake_decrypt(inpath, outpath, key, iv, progress_callback=None):
            for n in (10, 20, 30):
                progress_callback(n, 30)

        monkeypatch.setattr(bd.snowcrypt, "decrypt_aaxc", fake_decrypt)
        monkeypatch.setattr(
            bd._ProgressReporter,
            "report",
            lambda self, value, total=None, force=False: seen.append((value, total)),
        )

        aaxc = tmp_path / "in.aaxc"
        aaxc.write_bytes(b"x" * 30)
        entry = types.SimpleNamespace(id=1)

        service._decrypt_with_progress(entry, aaxc, tmp_path / "out.m4a", "kk", "ii")

        assert seen == [(10, 30), (20, 30), (30, 30)]

    def test_falls_back_to_watchdog_on_older_snowcrypt(self, monkeypatch, tmp_path, service):
        import app.services.book_download as bd

        monkeypatch.setattr(bd, "_SNOWCRYPT_REPORTS_PROGRESS", False)

        called = {}

        def fake_decrypt(inpath, outpath, key, iv):
            # No progress_callback kwarg: an older snowcrypt would raise
            # TypeError if we passed one.
            called["args"] = (inpath, outpath, key, iv)

        monkeypatch.setattr(bd.snowcrypt, "decrypt_aaxc", fake_decrypt)

        aaxc = tmp_path / "in.aaxc"
        aaxc.write_bytes(b"x" * 30)
        entry = types.SimpleNamespace(id=1)

        service._decrypt_with_progress(entry, aaxc, tmp_path / "out.m4a", "kk", "ii")

        assert called["args"][2:] == ("kk", "ii")

    def test_detection_matches_the_installed_snowcrypt(self):
        """
        Guards the feature detection itself: if snowcrypt's signature changes,
        this fails rather than silently falling back to the coarser watchdog.
        """
        import inspect

        import snowcrypt.snowcrypt as snowcrypt

        import app.services.book_download as bd

        expected = "progress_callback" in inspect.signature(
            snowcrypt.decrypt_aaxc
        ).parameters
        assert bd._SNOWCRYPT_REPORTS_PROGRESS is expected


class TestTruncationDetection:
    """
    A body that ends early must fail the download, not write a short file and
    let it reach the decrypter — where it surfaces as an opaque CBC padding
    error instead of "the file is incomplete".
    """

    def test_short_body_raises(self, monkeypatch, tmp_path, service):
        fake = _FakeStream([b"x" * 100], headers={"Content-Length": "1000"})
        fake.num_bytes_downloaded = 100
        _patch_stream(monkeypatch, fake)

        with pytest.raises(IOError, match="Truncated download"):
            service._download_file(
                "https://cloudfront.net/book.aaxc", tmp_path / "book.aaxc"
            )

    def test_error_names_both_sizes(self, monkeypatch, tmp_path, service):
        fake = _FakeStream([b"x" * 100], headers={"Content-Length": "1000"})
        fake.num_bytes_downloaded = 100
        _patch_stream(monkeypatch, fake)

        with pytest.raises(IOError) as excinfo:
            service._download_file(
                "https://cloudfront.net/book.aaxc", tmp_path / "book.aaxc"
            )

        assert "100" in str(excinfo.value)
        assert "1000" in str(excinfo.value)

    def test_complete_body_passes(self, monkeypatch, tmp_path, service):
        fake = _FakeStream([b"x" * 500, b"y" * 500], headers={"Content-Length": "1000"})
        fake.num_bytes_downloaded = 1000
        _patch_stream(monkeypatch, fake)

        out = tmp_path / "book.aaxc"
        service._download_file("https://cloudfront.net/book.aaxc", out)

        assert out.stat().st_size == 1000

    def test_no_content_length_is_not_treated_as_truncated(
        self, monkeypatch, tmp_path, service
    ):
        """Nothing to compare against, so the check can't run."""
        fake = _FakeStream([b"x" * 100])
        fake.num_bytes_downloaded = 100
        _patch_stream(monkeypatch, fake)

        out = tmp_path / "book.aaxc"
        service._download_file("https://cloudfront.net/book.aaxc", out)

        assert out.stat().st_size == 100

    def test_decoded_size_may_differ_from_content_length(
        self, monkeypatch, tmp_path, service
    ):
        """
        With a Content-Encoding, the header is the *encoded* length while
        iter_bytes yields decoded bytes. Comparing written bytes would raise on
        a perfectly good download, so the check uses the raw wire count.
        """
        fake = _FakeStream(
            [b"x" * 5000],
            headers={"Content-Length": "1000", "Content-Encoding": "gzip"},
        )
        fake.num_bytes_downloaded = 1000  # compressed bytes on the wire
        _patch_stream(monkeypatch, fake)

        out = tmp_path / "book.aaxc"
        service._download_file("https://cloudfront.net/book.aaxc", out)

        assert out.stat().st_size == 5000
