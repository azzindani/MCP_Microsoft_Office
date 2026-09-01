"""create_from_docx reported a clean success for a deck with no slides.

    "success": true, "slide_count": 0, "source_paragraph_count": 0,
    progress: ... "✔ Saved zeroslides.pptx", detail "0 slides"

Every tick green, no warning. Read back with something that did not write it,
the file has no `<p:sldIdLst>` and no slide parts at all; LibreOffice opens it
and renders one blank page. So it is not corrupt -- it is an empty deliverable
announced as a finished one, and `success` is the only field a caller is told
to check first.

data-visual's generate_chart already handles its own version of this
("output_path asked for '.png'; this tool writes HTML, so it was saved as
chart.html"). This is the same courtesy for an empty source.
"""

from __future__ import annotations

import docx

from pptx_new import engine


def _docx(path, paragraphs=()):
    d = docx.Document()
    for text in paragraphs:
        d.add_paragraph(text)
    d.save(str(path))
    return str(path)


def _warnings(result):
    return [p for p in result["progress"] if p.get("status") == "warn"]


def test_an_empty_source_still_succeeds(tmp_path):
    # The contract does not change: a valid file is still written.
    src = _docx(tmp_path / "empty.docx")
    out = tmp_path / "out.pptx"

    result = engine.create_from_docx(src, str(out), open_after=False)

    assert result["success"] is True
    assert result["slide_count"] == 0
    assert out.exists()


def test_an_empty_deck_is_reported_as_empty(tmp_path):
    src = _docx(tmp_path / "empty.docx")

    result = engine.create_from_docx(src, str(tmp_path / "out.pptx"), open_after=False)

    warns = _warnings(result)
    assert warns, "a deck with no slides was saved with nothing but green ticks"
    assert any("0 slides" in w.get("message", "") for w in warns)


def test_the_warning_says_why(tmp_path):
    # A hint that does not name the cause sends the caller looking at the
    # wrong end -- the source document is what was empty, not the writer.
    src = _docx(tmp_path / "empty.docx")

    result = engine.create_from_docx(src, str(tmp_path / "out.pptx"), open_after=False)

    detail = " ".join(w.get("detail", "") for w in _warnings(result))
    assert "empty.docx" in detail


def test_a_deck_with_slides_is_not_warned_about(tmp_path):
    src = _docx(tmp_path / "src.docx", ["First", "Second", "Third"])

    result = engine.create_from_docx(src, str(tmp_path / "out.pptx"), open_after=False)

    assert result["slide_count"] > 0
    assert not _warnings(result)


def test_the_empty_deck_really_has_no_slides(tmp_path):
    # Measured with a reader that did not write it: the finding was found this
    # way, and a content-presence check on the .pptx would have passed.
    import zipfile

    src = _docx(tmp_path / "empty.docx")
    out = tmp_path / "out.pptx"
    engine.create_from_docx(src, str(out), open_after=False)

    names = zipfile.ZipFile(out).namelist()
    assert not [n for n in names if n.startswith("ppt/slides/slide")]
