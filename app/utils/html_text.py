"""Convert the HTML fragments Audible returns into plain text.

Audible's `publisher_summary` is HTML (`<p>`, `<i>`, `<br>`, entities), but
descriptions from imported files are plain text, and every place we render a
description treats it as plain text. Normalizing at the edge keeps the two
sources looking the same.
"""

import re
from html import unescape
from html.parser import HTMLParser

# Tags that end a line of prose; everything else is inline.
_BLOCK_TAGS = {
    "p", "br", "div", "li", "ul", "ol", "tr", "table",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section", "article",
}

_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(value: str | None) -> str | None:
    """Strip HTML markup, leaving paragraph breaks as blank lines.

    Returns the value unchanged when it contains no markup, so plain-text
    descriptions pass through untouched.
    """
    if not value:
        return value

    if not _TAG_RE.search(value) and "&" not in value:
        return value

    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = unescape("".join(parser.parts))

    # Collapse runs of spaces/tabs, then runs of blank lines to one blank line.
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None
