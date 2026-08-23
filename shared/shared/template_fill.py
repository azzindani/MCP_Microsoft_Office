"""Plan a set of template substitutions so no key can corrupt another.

The template tools replaced each key in turn with a plain substring replace, in
whatever order the caller's dict happened to be in. Two keys where one contains
the other is enough to destroy the document:

    substitutions = {"platform": "Google Ads", "platform_spend": "1,939,003.26"}

    Platform: {platform}          ->  Platform: {Google Ads}
    Spend: {platform_spend}       ->  Spend: {Google Ads_spend}

    success: True, substitutions_applied: 3
    warn: "Placeholder 'platform_spend' not found in template"

Both failures are in that output. `platform` matched inside `platform_spend`
and ate it, and the warning then blamed the template for a placeholder the tool
had just destroyed. The braces survived because the caller passed bare names --
which the tool never says anything about, its docstring being 80 characters and
its `substitutions` schema an opaque dict.

So this module does two things:

* `resolve_targets` picks what to actually search for. A key present literally
  is used as-is. A key that only appears wrapped in one of the common
  placeholder delimiters is matched in that wrapped form, so a caller who
  passes `platform` against a `{platform}` template gets the braces replaced
  too instead of left behind.
* `ordered_pairs` returns those targets longest-first, which -- together with
  the two-phase sentinel replacement the docx path uses, and the single-pass
  regex the pptx path uses -- means a key can never consume another key or a
  value that an earlier replacement produced.
"""

from __future__ import annotations

import re

# Ordered by how specific they are, so `{{name}}` is preferred over `{name}`
# when a template happens to contain both wrappings of the same key.
DELIMITERS: tuple[tuple[str, str], ...] = (
    ("{{", "}}"),
    ("<<", ">>"),
    ("${", "}"),
    ("{", "}"),
    ("[[", "]]"),
    ("%", "%"),
)

# Private-use codepoints: not produced by any keyboard, not legal in a value a
# caller would send, and stable through python-docx and python-pptx round-trips.
_SENTINEL = "{}"


def resolve_targets(text: str, substitutions: dict) -> tuple[dict[str, str], list[str]]:
    """Map each key to the string to search for, plus notes about the mapping.

    Returns ({key: target}, notes). A key that matches nothing in any form is
    absent from the mapping -- the caller reports it as not found, and can now
    trust that verdict because nothing has been replaced yet.
    """
    targets: dict[str, str] = {}
    notes: list[str] = []
    for key in substitutions:
        raw = str(key)
        if not raw:
            continue
        # A delimited form wins over the bare literal, because the bare literal
        # is *inside* it: searching for `platform` against `{platform}` matches,
        # replaces the name and leaves the braces sitting in the document.
        wrapped_hit = next(
            (f"{o}{raw}{c}" for o, c in DELIMITERS if f"{o}{raw}{c}" in text),
            "",
        )
        if wrapped_hit:
            targets[raw] = wrapped_hit
            if wrapped_hit != raw:
                notes.append(f"Matched '{raw}' as '{wrapped_hit}' — the template delimits its placeholders")
        elif raw in text:
            targets[raw] = raw
    return targets, notes


def ordered_pairs(targets: dict[str, str], substitutions: dict) -> list[tuple[str, str]]:
    """(target, value) pairs, longest target first so no target is a prefix trap."""
    pairs = [(targets[str(k)], str(v)) for k, v in substitutions.items() if str(k) in targets]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def sentinel_for(index: int) -> str:
    """A placeholder no template or value can contain, for two-phase replacement.

    Phase one swaps every target for its sentinel, phase two swaps sentinels for
    values. Nothing a value contains can then be matched by a later target,
    which a single sequential pass cannot promise.
    """
    return _SENTINEL.format(index)


def substitute_once(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    """Replace every target in one pass. Returns (new_text, replacements_made).

    Used where the text is available as a plain string (a pptx run). The docx
    path cannot use this -- docxedit works run by run to keep formatting -- and
    uses sentinel_for() instead to get the same guarantee.
    """
    if not pairs:
        return text, 0
    lookup = dict(pairs)
    pattern = re.compile("|".join(re.escape(target) for target, _ in pairs))
    count = 0

    def _swap(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return lookup[match.group(0)]

    return pattern.sub(_swap, text), count
