"""Unit tests for the pure decision logic inside the services.

The services are mostly network and filesystem I/O, and chasing line coverage
through that is expensive and brittle. What is worth pinning is the logic that
decides things -- the match scoring, the filename sanitiser, the HTML-to-text
normaliser, the media-type table -- because those are where a silent wrong
answer is possible. A download that fails, fails loudly; a matcher that scores
the wrong book just quietly attaches a file to it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.book_matcher import BookMatcherService
from app.services.storage import normalise_endpoint
from app.utils.html_text import html_to_text
from app.utils.media_types import DEFAULT_AUDIO_MEDIA_TYPE, audio_media_type


# ---------------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------------


@pytest.fixture
def matcher(test_db: Session) -> BookMatcherService:
    return BookMatcherService(test_db)


def score(matcher, book, **file_metadata) -> float:
    return matcher._calculate_match_score(file_metadata, book)


class TestMatchScoring:
    """Title is 70% of the score, author and duration 15% each."""

    def test_exact_match_on_everything_scores_100(self, matcher, make_book):
        book = make_book(
            title="The Hobbit", author="J.R.R. Tolkien", duration_seconds=39600
        )
        assert (
            score(
                matcher,
                book,
                title="The Hobbit",
                author="J.R.R. Tolkien",
                duration_seconds=39600,
            )
            == 100.0
        )

    def test_scoring_is_case_insensitive(self, matcher, make_book):
        book = make_book(title="The Hobbit", author="Tolkien")
        assert score(matcher, book, title="THE HOBBIT", author="TOLKIEN") == score(
            matcher, book, title="the hobbit", author="tolkien"
        )

    def test_a_perfect_title_alone_reaches_the_default_threshold(
        self, matcher, make_book
    ):
        """find_matches defaults to a threshold of 85.

        Title is 70% of the score, so a title-only match tops out at 70 and must
        NOT clear the bar on its own. This is the test that stops a library full
        of same-titled books from being auto-matched on title alone.
        """
        book = make_book(title="The Hobbit", author="Tolkien", duration_seconds=39600)
        assert score(matcher, book, title="The Hobbit") == pytest.approx(70.0)

    def test_title_and_author_without_duration_clears_the_threshold(
        self, matcher, make_book
    ):
        book = make_book(title="The Hobbit", author="Tolkien", duration_seconds=39600)
        assert score(matcher, book, title="The Hobbit", author="Tolkien") == 85.0

    def test_completely_different_titles_score_low(self, matcher, make_book):
        book = make_book(title="The Hobbit", author="Tolkien")
        assert score(matcher, book, title="Dune", author="Herbert") < 40

    def test_missing_file_metadata_scores_zero(self, matcher, make_book):
        book = make_book(title="The Hobbit")
        assert score(matcher, book) == 0.0

    def test_none_metadata_is_tolerated(self, matcher, make_book):
        """scan_unassigned_files can yield a file it could not read tags from."""
        book = make_book(title="The Hobbit")
        assert matcher._calculate_match_score(None, book) == 0.0

    def test_missing_book_title_scores_zero_not_a_crash(self, matcher, make_book):
        book = make_book(title="x", author=None)
        book.title = None
        assert score(matcher, book, title="Anything") == 0.0


class TestDurationScoring:
    """Duration contributes 15%, tapering to nothing at a 5% difference."""

    @pytest.fixture
    def book(self, make_book):
        return make_book(title="", author=None, duration_seconds=10000)

    def test_exact_duration_scores_full(self, matcher, book):
        assert score(matcher, book, duration_seconds=10000) == pytest.approx(15.0)

    def test_one_percent_off_scores_most_of_it(self, matcher, book):
        # 1% diff -> 100 - (0.01 * 100 * 20) = 80 -> 80 * 0.15 = 12
        assert score(matcher, book, duration_seconds=10100) == pytest.approx(12.0)

    def test_five_percent_off_scores_nothing(self, matcher, book):
        """The 20x multiplier is chosen so 5% is exactly the cutoff."""
        assert score(matcher, book, duration_seconds=10500) == pytest.approx(0.0)

    def test_wildly_off_duration_does_not_go_negative(self, matcher, book):
        """max(0, ...) must hold, or a long file would drag a good title match
        below the threshold."""
        assert score(matcher, book, duration_seconds=1_000_000) >= 0.0

    def test_duration_difference_is_symmetric(self, matcher, book):
        assert score(matcher, book, duration_seconds=10100) == score(
            matcher, book, duration_seconds=9900
        )

    def test_zero_book_duration_is_skipped_not_divided_by(self, matcher, make_book):
        book = make_book(title="", author=None, duration_seconds=0)
        assert score(matcher, book, duration_seconds=1000) == 0.0

    def test_missing_durations_are_skipped(self, matcher, make_book):
        book = make_book(title="", author=None, duration_seconds=None)
        assert score(matcher, book, duration_seconds=1000) == 0.0


class TestFilenameSanitising:
    def test_keeps_ordinary_filenames(self, matcher):
        assert matcher._sanitize_filename("The Hobbit - Tolkien.m4b") == (
            "The Hobbit - Tolkien.m4b"
        )

    @pytest.mark.parametrize(
        "dangerous",
        ["../../etc/passwd", "/etc/passwd", "..\\..\\windows\\system32"],
    )
    def test_path_separators_are_removed(self, matcher, dangerous):
        """The result must not be usable to escape the target directory."""
        safe = matcher._sanitize_filename(dangerous)
        assert "/" not in safe
        assert "\\" not in safe

    def test_shell_metacharacters_are_removed(self, matcher):
        safe = matcher._sanitize_filename("book; rm -rf $HOME &.m4b")
        for ch in ";$&":
            assert ch not in safe

    def test_length_is_capped(self, matcher):
        assert len(matcher._sanitize_filename("a" * 500)) == 100

    def test_a_name_with_nothing_left_falls_back(self, matcher):
        """An all-punctuation name must still yield a usable filename."""
        assert matcher._sanitize_filename("///???") == "untitled"

    def test_empty_input_falls_back(self, matcher):
        assert matcher._sanitize_filename("") == "untitled"

    def test_unicode_is_preserved(self, matcher):
        """isalnum() is true for accented and non-Latin letters."""
        assert matcher._sanitize_filename("Émile Zola.m4b") == "Émile Zola.m4b"


# ---------------------------------------------------------------------------
# HTML normalisation
# ---------------------------------------------------------------------------


class TestHtmlToText:
    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_values_pass_through(self, value):
        assert html_to_text(value) == value

    def test_plain_text_is_returned_unchanged(self):
        """Descriptions imported from files are already plain text."""
        plain = "A perfectly ordinary description.  With two spaces."
        assert html_to_text(plain) == plain

    def test_tags_are_stripped(self):
        assert html_to_text("<p>Hello <i>world</i></p>") == "Hello world"

    def test_paragraphs_become_blank_lines(self):
        assert html_to_text("<p>One</p><p>Two</p>") == "One\n\nTwo"

    def test_br_breaks_the_line(self):
        assert "\n" in html_to_text("One<br>Two")

    def test_entities_are_unescaped(self):
        assert html_to_text("<p>Tom &amp; Jerry &mdash; &quot;hi&quot;</p>") == (
            'Tom & Jerry — "hi"'
        )

    def test_entities_are_unescaped_without_tags(self):
        """The no-markup shortcut must not skip entity decoding."""
        assert html_to_text("Tom &amp; Jerry") == "Tom & Jerry"

    def test_runs_of_blank_lines_collapse(self):
        assert "\n\n\n" not in html_to_text("<p>A</p><p></p><p></p><p>B</p>")

    def test_inline_tags_do_not_break_lines(self):
        assert html_to_text("<b>bold</b> and <i>italic</i>") == "bold and italic"

    def test_markup_that_leaves_nothing_returns_none(self):
        assert html_to_text("<p></p>") is None

    def test_list_items_are_separated(self):
        result = html_to_text("<ul><li>One</li><li>Two</li></ul>")
        assert "One" in result and "Two" in result
        assert "OneTwo" not in result


# ---------------------------------------------------------------------------
# Media types
# ---------------------------------------------------------------------------


class TestAudioMediaType:
    """Three places must agree or podcast players reject the episode: the RSS
    enclosure type, the stored B2 content type, and what the signed URL serves."""

    @pytest.mark.parametrize(
        "fmt,expected",
        [
            ("m4a", "audio/mp4"),
            ("m4b", "audio/x-m4b"),
            ("mp3", "audio/mpeg"),
        ],
    )
    def test_known_formats(self, fmt, expected):
        assert audio_media_type(fmt) == expected

    @pytest.mark.parametrize("variant", ["MP3", "Mp3", ".mp3", ".MP3"])
    def test_case_and_leading_dot_are_tolerated(self, variant):
        assert audio_media_type(variant) == "audio/mpeg"

    @pytest.mark.parametrize("value", [None, "", "flac", "wav"])
    def test_unknown_and_missing_fall_back(self, value):
        assert audio_media_type(value) == DEFAULT_AUDIO_MEDIA_TYPE


# ---------------------------------------------------------------------------
# B2 endpoint normalisation
# ---------------------------------------------------------------------------


class TestNormaliseEndpoint:
    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_become_none(self, value):
        assert normalise_endpoint(value) is None

    def test_a_bare_host_gains_https(self):
        """Backblaze displays the endpoint without a scheme; boto3 demands one."""
        assert normalise_endpoint("s3.us-west-002.backblazeb2.com") == (
            "https://s3.us-west-002.backblazeb2.com"
        )

    def test_an_existing_scheme_is_kept(self):
        assert normalise_endpoint("https://s3.example.com") == "https://s3.example.com"

    def test_http_is_not_silently_upgraded(self):
        """A local MinIO endpoint on http must keep working."""
        assert normalise_endpoint("http://localhost:9000").startswith("http://")

    def test_surrounding_whitespace_is_stripped(self):
        assert normalise_endpoint("  s3.example.com  ") == "https://s3.example.com"
