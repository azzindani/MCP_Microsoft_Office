"""A deleted slide must leave the .pptx, and a count must count the right thing.

**delete_slide only hid the slide.** It removed the entry from the presentation's
sldIdLst and stopped there, so every reader showed the right slide count --
PowerPoint and python-pptx both did -- while the slide part stayed inside the
package with a live relationship naming it. A sweep unzipped a deck after
deleting a slide and found `ppt/slides/slide4.xml` still shipping with all its
text, and `_rels/presentation.xml.rels` still carrying `rId9 ->
slides/slide4.xml`. Anyone handed the file could read what had been deleted
from it, which for a deck circulated after removing a slide is the entire point
of removing it.

Dropping the relationship drops the part with it: the package serialiser writes
only what is still reachable.

**create_from_template miscounted.** `_substitute_in_text_frame` threw away the
count `substitute_once` returns and added 1 per *run touched* instead. A slide
reading "Channel {channel} delivered {impressions} impressions with CTR {ctr}"
is one run, so all three placeholders were filled correctly and the response
said `substitutions_applied: 1`. The file was right and the number was not,
which is the harder kind to notice.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "shared"), str(ROOT / "servers" / "pptx_basic"), str(ROOT / "servers" / "pptx_new")):
    if p not in sys.path:
        sys.path.insert(0, p)

from pptx_basic import engine as basic  # noqa: E402
from pptx_new import engine as new  # noqa: E402

SECRET = "confidential revenue 54000"


@pytest.fixture
def deck(tmp_path):
    p = tmp_path / "deck.pptx"
    r = new.create_presentation(str(p), "Deck", "sub", open_after=False)
    assert r["success"] is True, r.get("error")
    for title, body in [("Keep A", "body a"), ("SECRET", SECRET), ("Keep B", "body b")]:
        assert basic.add_slide(str(p), "Title and Content", title, body)["success"] is True
    return p


def parts(p: Path) -> list[str]:
    return sorted(n for n in zipfile.ZipFile(p).namelist() if n.startswith("ppt/slides/slide"))


class TestDeleteSlideRemovesTheSlide:
    def test_the_part_is_gone_from_the_package(self, deck):
        before = parts(deck)
        assert len(before) == 4
        r = basic.delete_slide(str(deck), 2)
        assert r["success"] is True, r.get("error")
        assert len(parts(deck)) == 3, "the slide part is still in the zip"

    def test_its_text_is_gone_from_the_bytes(self, deck):
        basic.delete_slide(str(deck), 2)
        z = zipfile.ZipFile(deck)
        blob = b"".join(z.read(n) for n in z.namelist())
        assert SECRET.encode() not in blob, "deleted content is still readable in the file"

    def test_no_relationship_still_points_at_it(self, deck):
        basic.delete_slide(str(deck), 2)
        rels = zipfile.ZipFile(deck).read("ppt/_rels/presentation.xml.rels").decode()
        assert rels.count("slides/slide") == 3, rels

    def test_the_slides_that_stay_are_untouched(self, deck):
        basic.delete_slide(str(deck), 2)
        r = basic.read_presentation(str(deck))
        titles = [s.get("title") for s in r["slides"]]
        assert "SECRET" not in titles
        assert "Keep A" in titles and "Keep B" in titles

    def test_the_file_still_opens(self, deck):
        basic.delete_slide(str(deck), 2)
        # A dropped relationship that took too much with it would show up here.
        assert basic.read_presentation(str(deck))["success"] is True


class TestSubstitutionsAreCounted:
    def test_three_placeholders_in_one_run_count_as_three(self, tmp_path):
        template = tmp_path / "t.pptx"
        r = new.create_presentation(str(template), "T", "sub", open_after=False)
        assert r["success"] is True, r.get("error")
        assert (
            basic.add_slide(
                str(template),
                "Title and Content",
                "Summary",
                "Channel {channel} delivered {impressions} impressions with CTR {ctr}.",
            )["success"]
            is True
        )

        out = tmp_path / "filled.pptx"
        r = new.create_from_template(
            str(template),
            str(out),
            {"channel": "Social", "impressions": "15000", "ctr": "0.042"},
            open_after=False,
        )
        assert r["success"] is True, r.get("error")
        assert r["substitutions_applied"] == 3, r

        text = basic.read_slide_text(str(out), 1)
        joined = str(text)
        assert "Social" in joined and "15000" in joined and "0.042" in joined
        assert "{" not in joined.replace("{'", "").replace('{"', ""), "a placeholder survived"
