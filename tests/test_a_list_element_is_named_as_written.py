"""A wrong list element is named as the caller wrote it, not as a misspelling.

feature_engineering(features=[{...}]) with one element of the wrong type was
answered "Did you mean features=?" -- asking a caller who had used exactly that
name. pydantic names an element by its path, `features.0`, which is not an
argument name, so shared/arg_errors took it for a typo. It names the element
now -- features[0] -- and says to correct its type. shared/arg_errors.py is
byte-identical across the fleet (File_System keeps its own formatting).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from shared.arg_errors import _refusal  # type: ignore[reportMissingImports]

KNOWN = ["features", "dataset"]


class _Model(BaseModel):
    features: list[dict]
    dataset: list[float]


def _refused(payload: dict) -> dict:
    with pytest.raises(ValidationError) as exc:
        _Model(**payload)
    return _refusal("some_tool", KNOWN, str(exc.value))


class TestAnElementIsNotAMisspelling:
    def test_a_wrong_element_is_named_by_its_index(self):
        answer = _refused({"features": ["not a dict"], "dataset": [1.0]})
        assert "features[0]" in answer["error"] and "features[0]" in answer["hint"]
        assert "Did you mean" not in answer["hint"]

    def test_a_later_element_too(self):
        answer = _refused({"features": [{}], "dataset": [1.0, "two"]})
        assert "dataset[1]" in answer["hint"] and "Did you mean" not in answer["hint"]

    def test_a_missing_argument_is_still_named(self):
        answer = _refused({"dataset": [1.0]})
        assert answer["hint"].startswith("features is required")
