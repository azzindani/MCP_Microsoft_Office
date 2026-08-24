"""Accept the name a caller would reasonably have guessed for an argument.

Across the Office servers one concept is nearly always spelled one way. A
census of every `@mcp.tool()` signature in the repo:

    the sheet     sheet_name       28    source_sheet 1    old_name 1
    the slide     slide_index      10
    the paragraph paragraph_index   5    index        1

`slide_index` is the control: ten tools, one spelling, and no sweep has ever
mis-called one. The outliers are where phases stall. A sweep model called
rename_sheet(old_name=..., new_name=...) and then, two tools later, wrote
`new_name` for copy_sheet -- which takes `new_sheet_name`:

    Error executing tool copy_sheet: 1 validation error for copy_sheetArguments
    new_sheet_name
      Field required [type=missing, ...]

pydantic refuses that before any server code runs, so the tool cannot suggest
the name it wanted; and the schema carries no property descriptions, so the
parameter name is the whole contract. The same shape cost a phase three
attempts on read_table_row and another on add_pivot_table.

Renaming the outliers would fix the guess and break every existing caller, so
instead each one accepts both spellings and resolves here. The canonical name
is the one the other 28 tools use, so a caller who follows the majority
convention is always right.
"""

from __future__ import annotations


def pick(op: str, field: str, primary: str, alias: str) -> tuple[str, str]:
    """Resolve one argument given under either spelling.

    Returns (value, note). `note` is empty unless the alias was used, in which
    case it names both spellings so the progress log records what happened.
    Returns ("", note) with a non-empty note when neither was given -- callers
    turn that into their own error dict rather than raising.
    """
    chosen = primary.strip() or alias.strip()
    if not chosen:
        return "", f"{op} needs {field}: pass {field}= (also accepted: the alias form)"
    if not primary.strip() and alias.strip():
        return chosen, f"Read {field} from the alias spelling; {field}= is the documented one"
    return chosen, ""


# The same problem one level down, inside a list[dict]. `paragraphs`,
# `sections`, `slides` and `data_slides` are bare list[dict] in their schemas,
# so pydantic never sees the keys and nothing refuses a wrong one -- the entry
# is built from a .get() default and the document comes out short:
#
#     create_from_text(paragraphs=[{"content": "hello"}])
#     -> success: true, "1 paragraphs written", and a .docx with no text in it
#
#     create_from_sections(sections=[{"header": "H", "body": "B"}])
#     -> success: true, and a document whose headings are all missing
#
# pptx_new already aliases its own keys and warns on an entry it cannot name;
# docx_new was written the same week and never got either. These are shared so
# the next module cannot be the one that misses out.
ENTRY_TEXT_KEYS: tuple[str, ...] = ("text", "content", "body", "paragraph", "value")
ENTRY_HEADING_KEYS: tuple[str, ...] = ("heading", "title", "header", "name")
ENTRY_BULLET_KEYS: tuple[str, ...] = ("bullets", "items", "points", "lines", "content", "body", "text")


def entry_value(item: dict, keys: tuple[str, ...]) -> str:
    """The first non-empty value under any accepted spelling, as text."""
    if not isinstance(item, dict):
        return str(item) if item else ""
    for key in keys:
        value = item.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list | tuple):
            return "\n".join(str(v) for v in value)
        return str(value)
    return ""


def unnamed_entry_note(index: int, item: dict, keys: tuple[str, ...], label: str) -> str:
    """Why this entry contributed nothing, or "" if it carried something.

    An entry whose keys are all unrecognised is a typo every time -- nobody
    passes a dict meaning "add a blank one" -- so it is worth saying out loud
    rather than writing an empty paragraph and counting it as written.
    """
    if not isinstance(item, dict):
        return "" if item else f"{label} {index} is empty"
    if entry_value(item, keys):
        return ""
    seen = ", ".join(sorted(map(str, item))) or "none"
    return f"{label} {index} has no {keys[0]}: keys seen are {seen} — accepted: {', '.join(keys)}"


def missing(op: str, field: str, alias: str) -> dict:
    """The error dict for an argument given under neither spelling."""
    return {
        "success": False,
        "op": op,
        "error": f"{op} needs a {field}",
        "hint": f"Pass {field}=. The older spelling {alias}= is still accepted.",
        "progress": [],
        "token_estimate": 20,
    }
