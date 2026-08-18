"""Normalise body text before it goes into a PowerPoint placeholder.

A content placeholder draws its own bullet glyph for every paragraph. Callers —
LLMs especially — write list markers into the text anyway, because that is how a
list looks everywhere else. The result renders as "• • Point 1": one bullet from
the layout, one from the string. Found by rendering a generated deck to PDF and
looking at it; the file was valid OOXML and every tool reported success.
"""

from __future__ import annotations

import re

# A marker only counts when whitespace and real content follow it, so "-5 °C"
# and "*emphasis*" survive untouched.
_LIST_MARKER = re.compile(r"^[•‣◦⁃∙*–—-]\s+(?=\S)")


def strip_list_markers(text: str) -> str:
    """Remove one leading list marker from each line of `text`.

    Nested markers are left alone beyond the first: "- - x" becomes "- x", which
    is what someone writing a sub-item meant.
    """
    if not text:
        return text
    return "\n".join(_LIST_MARKER.sub("", line.rstrip()) for line in text.split("\n"))
