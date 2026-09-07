"""Put a parameter's legal values in the schema, where the caller can read them.

Round 28 censused all 244 tools and found 55 parameters whose whole job is to
select behaviour -- `action`, `mode`, `method`, `agg_func`, `chart_type`,
`task`, `how`, `format` -- and **not one declared an `enum`**. Every legal value
existed only in prose, and often not even there: `fs_manage`'s docstring reads
"Disk usage, permissions, symlink info, or snapshot version list" while the
tokens are `disk_usage`, `permissions`, `symlink_info`, `versions`. A caller had
to guess the exact spelling from English and learned it by burning a call.

That round fixed the runtime -- five parameters were answering a value they
could not read -- and deferred the schema, because the obvious mechanism is
wrong here.

**Why not `Literal`.** Measured on the bundled FastMCP, `Literal["a","b"]` and
`Annotated[str, Field(json_schema_extra={"enum": ["a","b"]})]` emit the *same*
JSON schema:

    {"default": "a", "enum": ["a", "b"], "title": "Mode", "type": "string"}

so both deliver the entire client-facing benefit. They differ in what happens to
a value outside the set. `Literal` makes pydantic reject it before the tool body
runs, which costs two things this fleet has spent twenty-eight rounds building:

* **the aliases.** `zscore` for `std`, `average` for `mean`, `MoM` for `M`,
  `==` for `equals`, `xlsx` for `excel`. Each exists because a caller reached
  for it first and being refused for a vocabulary difference is a wasted turn.
  A `Literal` listing only the canonical names breaks every one; a `Literal`
  listing the aliases too turns a five-value enum into a fourteen-value wall
  and stops being the readable answer it was added to be.
* **the refusals.** `train_regressor(model="lr")` answers *"Unknown model:
  'lr'. Allowed: dtr, lar, lir, pr, rfr, rr, xgb"* with the hint *"'lr' is a
  train_classifier() model. Pick one listed above, or call
  train_classifier()."* -- the best error message in the fleet, and pydantic
  would answer first with a generic literal_error instead.

So the enum here **advertises** rather than enforces: the schema names the
canonical values, the client validates against them and never sends a wrong one,
and a value that does arrive still reaches the tool, which knows about aliases
and can say something useful. The runtime is the authority; this is the
signpost.

Render the values from the table the runtime switches on -- never a second copy.
The cause of a chain of defects in this fleet has twice been a second table
whose copies drifted.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any

from pydantic import Field


def one_of(*values: str) -> Any:
    """A string parameter whose legal values the schema names.

        mode: one_of("content", "tree", "meta", "diff", "auto") = "auto"

    Advertised, not enforced -- see the module docstring. Order is preserved,
    so list them the way a caller should read them rather than alphabetically
    when one of them is the obvious default.
    """
    return Annotated[str, Field(json_schema_extra={"enum": list(values)})]


def any_of(values: Iterable[str]) -> Any:
    """`one_of` for a set that is computed rather than written out.

    Used where the runtime's own table is the source -- ALLOWED_OPS, the
    classifier and regressor registries -- so the schema cannot drift from it.
    """
    return one_of(*sorted(values))
