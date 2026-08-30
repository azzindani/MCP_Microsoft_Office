"""Three-state flags for tools that must be able to turn something OFF.

`bold: bool = False` cannot express "leave it alone". False is a real value, so
the tool has no way to tell "the caller wants this not-bold" from "the caller
did not mention bold", and every implementation in this repo resolved that the
same way:

    if bold:
        run.font.bold = True

which makes bold a **write-only-on** flag. `set_font_all_slides(bold=False)`
returned success with `shapes_modified: 6` and echoed `"bold": false` back,
while the run stayed bold on read-back -- the response asserting a value it had
not written. There was no way, through any argument, to un-bold text.

The neighbouring arguments do not have this problem because their types carry a
value outside the useful range: `font_name=""` and `font_size=0` are genuinely
"unset". A bool has no such value, and `Optional[bool]` is banned as a parameter
type (CLAUDE.md §16), so the three states have to be spelled.

    ""       leave whatever the document already has
    "true"   turn it on
    "false"  turn it off

This is a deliberate schema change: a caller passing a JSON boolean now gets a
validation error naming the three values, instead of an argument that was
accepted, ignored, and reported as applied.
"""

from __future__ import annotations

LEAVE = ""
ON = "true"
OFF = "false"

# Spelled out rather than accepting anything truthy. "yes", "1" and "on" all
# read as true to a person and are all easy to typo into something that is not
# in the set; an explicit list means a wrong value is an error rather than a
# silent False.
_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}


class TriStateError(ValueError):
    """Raised with the hint a tool hands straight back to the caller."""

    def __init__(self, name: str, value: str) -> None:
        super().__init__(f"{name}={value!r} is not one of '', 'true' or 'false'")
        self.hint = (
            f"Pass {name}='true' to turn it on, {name}='false' to turn it off, "
            f"or leave {name} out to keep whatever the document already has."
        )


def parse(value: str, name: str) -> bool | None:
    """'' -> None (leave), 'true' -> True, 'false' -> False.

    None means LEAVE, and callers must test `is not None` rather than
    truthiness -- `if flag:` would skip False and reintroduce exactly the bug
    this module exists to remove.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise TriStateError(name, value)


def echo(value: bool | None) -> str:
    """The parsed state as it should appear in the response.

    Reported as what was DONE, never as what was passed. The defect this
    module fixes was visible in the response before it was visible in the
    file: `"bold": false` sat in a successful reply beside text that was still
    bold, because the tool echoed its argument instead of its effect.
    """
    if value is None:
        return "unchanged"
    return ON if value else OFF
