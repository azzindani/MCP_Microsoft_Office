"""Tests for pptx_basic engine."""

import shutil
from pathlib import Path

import pytest

from pptx_basic.engine import (
    add_slide,
    add_text_box,
    delete_slide,
    diff_versions,
    read_presentation,
    read_slide,
    read_slide_text,
    reorder_slide,
    search_slides,
    set_text,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def deck_path() -> Path:
    return FIXTURES_DIR / "deck_simple.pptx"


@pytest.fixture
def tmp_deck(tmp_path: Path, deck_path: Path) -> Path:
    """Writable copy of deck_simple.pptx in a temp directory."""
    target = tmp_path / "deck_simple.pptx"
    shutil.copy(deck_path, target)
    return target


# ─── read_presentation ───────────────────────────────────────────────────────


def test_read_presentation_returns_slide_count(deck_path: Path) -> None:
    result = read_presentation(str(deck_path))
    assert result["success"] is True
    assert result["slide_count"] == 5


def test_read_presentation_returns_layouts(deck_path: Path) -> None:
    result = read_presentation(str(deck_path))
    assert result["success"] is True
    assert isinstance(result["available_layouts"], list)
    assert len(result["available_layouts"]) > 0
    assert "Title Slide" in result["available_layouts"]


def test_read_presentation_returns_slides_list(deck_path: Path) -> None:
    result = read_presentation(str(deck_path))
    assert result["success"] is True
    slides = result["slides"]
    assert len(slides) == 5
    assert slides[0]["index"] == 0
    assert "title" in slides[0]
    assert "shape_count" in slides[0]
    assert "has_table" in slides[0]
    assert "has_chart" in slides[0]


def test_read_presentation_has_progress(deck_path: Path) -> None:
    result = read_presentation(str(deck_path))
    assert "progress" in result
    assert isinstance(result["progress"], list)


def test_read_presentation_file_not_found() -> None:
    result = read_presentation("/nonexistent/path/deck.pptx")
    assert result["success"] is False
    assert "progress" in result
    assert "error" in result


def test_read_presentation_wrong_type(tmp_path: Path) -> None:
    fake = tmp_path / "not_a_deck.docx"
    fake.write_bytes(b"fake")
    result = read_presentation(str(fake))
    assert result["success"] is False
    assert ".docx" in result["error"]


# ─── read_slide ──────────────────────────────────────────────────────────────


def test_read_slide_returns_shapes(deck_path: Path) -> None:
    result = read_slide(str(deck_path), 0)
    assert result["success"] is True
    assert isinstance(result["shapes"], list)
    assert len(result["shapes"]) > 0


def test_read_slide_returns_shape_names(deck_path: Path) -> None:
    result = read_slide(str(deck_path), 0)
    assert result["success"] is True
    names = [s["name"] for s in result["shapes"]]
    assert "Title 1" in names


def test_read_slide_returns_shape_index(deck_path: Path) -> None:
    result = read_slide(str(deck_path), 0)
    assert result["success"] is True
    for i, shape in enumerate(result["shapes"]):
        assert shape["index"] == i


def test_read_slide_out_of_range(deck_path: Path) -> None:
    result = read_slide(str(deck_path), 99)
    assert result["success"] is False
    assert "progress" in result


def test_read_slide_has_progress(deck_path: Path) -> None:
    result = read_slide(str(deck_path), 1)
    assert "progress" in result
    assert isinstance(result["progress"], list)


# ─── search_slides ────────────────────────────────────────────────────────────


def test_search_slides_finds_match(deck_path: Path) -> None:
    result = search_slides(str(deck_path), "Revenue")
    assert result["success"] is True
    assert len(result["matches"]) > 0
    slide_indices = [m["slide_index"] for m in result["matches"]]
    assert 1 in slide_indices  # "Revenue Performance" is slide 1


def test_search_slides_no_match(deck_path: Path) -> None:
    result = search_slides(str(deck_path), "ZZZNOMATCH_XYZ")
    assert result["success"] is True
    assert result["matches"] == []


def test_search_slides_empty_query(deck_path: Path) -> None:
    result = search_slides(str(deck_path), "")
    assert result["success"] is False
    assert "progress" in result


def test_search_slides_returns_total_scanned(deck_path: Path) -> None:
    result = search_slides(str(deck_path), "Q3")
    assert result["success"] is True
    assert result["total_slides_scanned"] == 5


def test_search_slides_has_progress(deck_path: Path) -> None:
    result = search_slides(str(deck_path), "Revenue")
    assert "progress" in result
    assert isinstance(result["progress"], list)


# ─── read_slide_text ─────────────────────────────────────────────────────────


def test_read_slide_text_returns_text(deck_path: Path) -> None:
    result = read_slide_text(str(deck_path), 0)
    assert result["success"] is True
    assert isinstance(result["shapes"], list)
    texts = [s["text"] for s in result["shapes"]]
    assert any("Q3" in t for t in texts)


def test_read_slide_text_has_progress(deck_path: Path) -> None:
    result = read_slide_text(str(deck_path), 0)
    assert "progress" in result
    assert isinstance(result["progress"], list)


def test_read_slide_text_out_of_range(deck_path: Path) -> None:
    result = read_slide_text(str(deck_path), 100)
    assert result["success"] is False
    assert "progress" in result


# ─── set_text ────────────────────────────────────────────────────────────────


def test_set_text_replaces_title(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 0, "Title 1", "Updated Title")
    assert result["success"] is True
    assert result["new_text"] == "Updated Title"

    # Verify the change persisted
    verify = read_slide_text(str(tmp_deck), 0)
    texts = [s["text"] for s in verify["shapes"]]
    assert any("Updated Title" in t for t in texts)


def test_set_text_creates_snapshot(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 0, "Title 1", "Snapshot Test")
    assert result["success"] is True
    assert "backup" in result
    backup_path = Path(result["backup"])
    assert backup_path.exists()


def test_set_text_shape_not_found_error(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 0, "NonExistentShape999", "text")
    assert result["success"] is False
    assert "not found" in result["error"]
    assert "progress" in result


def test_set_text_has_progress(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 0, "Title 1", "Progress Test")
    assert "progress" in result
    assert isinstance(result["progress"], list)
    assert len(result["progress"]) > 0


def test_set_text_out_of_range_slide(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 99, "Title 1", "text")
    assert result["success"] is False
    assert "progress" in result


def test_set_text_returns_old_text(tmp_deck: Path) -> None:
    result = set_text(str(tmp_deck), 0, "Title 1", "New Title")
    assert result["success"] is True
    assert "old_text" in result
    assert result["old_text"] == "Q3 2026 Business Review"


# ─── add_slide ───────────────────────────────────────────────────────────────


def test_add_slide_appends(tmp_deck: Path) -> None:
    before = read_presentation(str(tmp_deck))
    count_before = before["slide_count"]

    result = add_slide(str(tmp_deck), "Title and Content", "New Slide", "Body text here")
    assert result["success"] is True
    assert result["slide_index"] == count_before

    after = read_presentation(str(tmp_deck))
    assert after["slide_count"] == count_before + 1


def test_add_slide_invalid_layout_error(tmp_deck: Path) -> None:
    result = add_slide(str(tmp_deck), "NONEXISTENT LAYOUT XYZ", "title")
    assert result["success"] is False
    assert "not found" in result["error"]
    assert "progress" in result


def test_add_slide_creates_snapshot(tmp_deck: Path) -> None:
    result = add_slide(str(tmp_deck), "Blank")
    assert result["success"] is True
    assert "backup" in result
    backup_path = Path(result["backup"])
    assert backup_path.exists()


def test_add_slide_has_progress(tmp_deck: Path) -> None:
    result = add_slide(str(tmp_deck), "Title Slide", "Test")
    assert "progress" in result
    assert isinstance(result["progress"], list)


def test_add_slide_with_title_sets_title(tmp_deck: Path) -> None:
    add_slide(str(tmp_deck), "Title and Content", "My New Title", "Body")
    prs_result = read_presentation(str(tmp_deck))
    last_slide_idx = prs_result["slide_count"] - 1
    slide_text = read_slide_text(str(tmp_deck), last_slide_idx)
    texts = [s["text"] for s in slide_text["shapes"]]
    assert any("My New Title" in t for t in texts)


# ─── delete_slide ────────────────────────────────────────────────────────────


def test_delete_slide_removes(tmp_deck: Path) -> None:
    before = read_presentation(str(tmp_deck))
    count_before = before["slide_count"]

    result = delete_slide(str(tmp_deck), 0)
    assert result["success"] is True
    assert result["deleted_index"] == 0
    assert result["remaining_slides"] == count_before - 1

    after = read_presentation(str(tmp_deck))
    assert after["slide_count"] == count_before - 1


def test_delete_slide_creates_snapshot(tmp_deck: Path) -> None:
    result = delete_slide(str(tmp_deck), 0)
    assert result["success"] is True
    assert "backup" in result
    backup_path = Path(result["backup"])
    assert backup_path.exists()


def test_delete_slide_out_of_range(tmp_deck: Path) -> None:
    result = delete_slide(str(tmp_deck), 99)
    assert result["success"] is False
    assert "progress" in result


def test_delete_slide_has_progress(tmp_deck: Path) -> None:
    result = delete_slide(str(tmp_deck), 4)
    assert "progress" in result
    assert isinstance(result["progress"], list)


# ─── reorder_slide ───────────────────────────────────────────────────────────


def test_reorder_slide_moves(tmp_deck: Path) -> None:
    # Get the title of slide 0 before reorder
    before_slide0 = read_slide_text(str(tmp_deck), 0)
    title_was_at_0 = before_slide0["shapes"][0]["text"]

    result = reorder_slide(str(tmp_deck), 0, 2)
    assert result["success"] is True
    assert result["from_index"] == 0
    assert result["to_index"] == 2

    # The slide that was at index 0 should now be at index 2
    after_slide2 = read_slide_text(str(tmp_deck), 2)
    texts = [s["text"] for s in after_slide2["shapes"]]
    assert any(title_was_at_0 in t for t in texts)


def test_reorder_slide_creates_snapshot(tmp_deck: Path) -> None:
    result = reorder_slide(str(tmp_deck), 0, 1)
    assert result["success"] is True
    assert "backup" in result
    backup_path = Path(result["backup"])
    assert backup_path.exists()


def test_reorder_slide_same_index_noop(tmp_deck: Path) -> None:
    result = reorder_slide(str(tmp_deck), 2, 2)
    assert result["success"] is True
    assert "No change" in result.get("message", "")


def test_reorder_slide_out_of_range(tmp_deck: Path) -> None:
    result = reorder_slide(str(tmp_deck), 99, 0)
    assert result["success"] is False
    assert "progress" in result


def test_reorder_slide_has_progress(tmp_deck: Path) -> None:
    result = reorder_slide(str(tmp_deck), 0, 1)
    assert "progress" in result
    assert isinstance(result["progress"], list)


# ─── add_text_box ────────────────────────────────────────────────────────────


def test_add_text_box(tmp_deck: Path) -> None:
    result = add_text_box(str(tmp_deck), 0, "Hello from text box")
    assert result["success"] is True
    assert result["text"] == "Hello from text box"


def test_add_text_box_creates_snapshot(tmp_deck: Path) -> None:
    result = add_text_box(str(tmp_deck), 0, "snapshot test")
    assert result["success"] is True
    assert "backup" in result
    backup_path = Path(result["backup"])
    assert backup_path.exists()


def test_add_text_box_has_progress(tmp_deck: Path) -> None:
    result = add_text_box(str(tmp_deck), 0, "progress test")
    assert "progress" in result
    assert isinstance(result["progress"], list)


def test_add_text_box_custom_position(tmp_deck: Path) -> None:
    result = add_text_box(str(tmp_deck), 1, "positioned box", left=2.0, top=3.0, width=4.0, height=0.5)
    assert result["success"] is True
    assert result["position"]["left"] == 2.0
    assert result["position"]["top"] == 3.0


def test_add_text_box_out_of_range(tmp_deck: Path) -> None:
    result = add_text_box(str(tmp_deck), 99, "text")
    assert result["success"] is False
    assert "progress" in result


# ─── diff_versions ───────────────────────────────────────────────────────────


def test_diff_versions_returns_summary(tmp_deck: Path) -> None:
    # Make a change to create a snapshot
    set_text(str(tmp_deck), 0, "Title 1", "Modified Title")

    # Get history
    from shared.version_control import get_history

    history = get_history(str(tmp_deck))
    assert len(history) >= 1

    result = diff_versions(str(tmp_deck), history[0]["timestamp"])
    assert result["success"] is True
    assert "summary" in result
    assert isinstance(result["summary"], str)


def test_diff_versions_detects_changed_shape_text(tmp_deck: Path) -> None:
    # Make a change to create a snapshot
    set_text(str(tmp_deck), 0, "Title 1", "Changed Title for Diff")

    from shared.version_control import get_history

    history = get_history(str(tmp_deck))
    # timestamp_a is the backup (before), timestamp_b defaults to current
    result = diff_versions(str(tmp_deck), history[0]["timestamp"])
    assert result["success"] is True
    assert result["change_count"] > 0


def test_diff_versions_invalid_timestamp(tmp_deck: Path) -> None:
    result = diff_versions(str(tmp_deck), "9999-99-99T99-99-99Z")
    assert result["success"] is False
    assert "progress" in result


def test_diff_versions_has_progress(tmp_deck: Path) -> None:
    # Create a snapshot first
    set_text(str(tmp_deck), 0, "Title 1", "Diff Progress Test")

    from shared.version_control import get_history

    history = get_history(str(tmp_deck))
    result = diff_versions(str(tmp_deck), history[0]["timestamp"])
    assert "progress" in result
    assert isinstance(result["progress"], list)


# ─── All responses have progress field ───────────────────────────────────────


def test_all_responses_have_progress_field(deck_path: Path, tmp_deck: Path) -> None:
    """Every tool response must include a 'progress' key."""
    responses = [
        read_presentation(str(deck_path)),
        read_slide(str(deck_path), 0),
        search_slides(str(deck_path), "Revenue"),
        read_slide_text(str(deck_path), 0),
        set_text(str(tmp_deck), 0, "Title 1", "Progress Check"),
        add_slide(str(tmp_deck), "Blank"),
        delete_slide(str(tmp_deck), 4),
        reorder_slide(str(tmp_deck), 0, 1),
        add_text_box(str(tmp_deck), 0, "test"),
        # diff_versions requires a snapshot — skipped here for simplicity
        read_presentation("/nonexistent/path.pptx"),  # error case
        search_slides(str(deck_path), ""),  # error case
    ]

    for i, resp in enumerate(responses):
        assert "progress" in resp, f"Response {i} missing 'progress' key: {resp}"
