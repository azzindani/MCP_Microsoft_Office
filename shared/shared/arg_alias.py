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
