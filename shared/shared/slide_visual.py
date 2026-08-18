"""Geometry and contrast checks for slides — the two ways a deck goes wrong silently.

Both defects here were found by rendering a generated deck to PDF and looking at
it. Every tool involved returned success:true and the file was structurally
valid python-pptx output.

1. Placement is unchecked. `add_chart` takes left/top/width/height in inches and
   hands them straight to python-pptx, which will happily place a shape past the
   edge of the slide. The chart was drawn with its lower half beyond the canvas:
   two of the five category labels were cut off, and nothing in the result said
   so.

2. Colour is unchecked. `set_background` sets one slide at a time, while
   `set_font_all_slides` paints every slide. Set a dark background on slide 1 and
   white text everywhere, and slide 2 gets white text on a white background --
   the title is still there, still "successfully" applied, and completely
   invisible.

Neither of these can be caught by asserting on the return value, so the checks
belong next to the operations that cause them.
"""

from __future__ import annotations

# WCAG 2.1 contrast ratios. 4.5 is the AA threshold for body text and 3.0 for
# large text; a deck title is large, so 3.0 is the line that matters here.
# Anything at or below ~1.3 is effectively the same colour.
MIN_CONTRAST = 3.0
INVISIBLE_CONTRAST = 1.3


def _channel(value: float) -> float:
    """Linearise one sRGB channel for the luminance formula."""
    value = value / 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a 6-digit hex colour."""
    clean = hex_color.lstrip("#")
    r, g, b = (int(clean[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Return the WCAG contrast ratio between two hex colours (1.0 to 21.0)."""
    a, b = relative_luminance(fg_hex), relative_luminance(bg_hex)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def slide_background_hex(slide) -> str | None:
    """Return the slide's own solid background colour, or None if it inherits.

    The slide's own fill wins; failing that the layout's, then the master's.
    Returns None only when nothing in that chain sets a solid fill.

    Resolving the chain matters more than it looks. The deck that prompted this
    had its unreadable slide left at the template default -- white by
    inheritance, not by an explicit fill -- so a check that only looked at the
    slide itself saw nothing and missed the very bug it was written for.
    """
    # Imported here rather than at module scope: shared/ is also imported by the
    # docx and xlsx servers, which have no reason to pull in python-pptx.
    from pptx.enum.dml import MSO_FILL

    for source in (slide, getattr(slide, "slide_layout", None), getattr(slide, "slide_master", None)):
        if source is None:
            continue
        try:
            fill = source.background.fill
            # Anything other than SOLID (usually BACKGROUND) means "inherit",
            # so fall through to the next level of the chain.
            if fill.type == MSO_FILL.SOLID:
                return str(fill.fore_color.rgb)
        except (AttributeError, TypeError, ValueError):
            continue
    return None


# PowerPoint renders a slide with nothing set anywhere in its inheritance chain
# on white. Assuming that is a guess, but it is the correct guess for every
# default-template deck, and the alternative -- staying silent -- is what let
# white-on-white text ship in the first place. Offenders found this way are
# flagged `assumed` so the caller can tell the two apart.
_DEFAULT_BACKGROUND = "FFFFFF"


def unreadable_slides(prs, color_hex: str) -> list[dict]:
    """Return the slides where `color_hex` text would be hard or impossible to read."""
    clean = color_hex.lstrip("#").upper()
    offenders: list[dict] = []
    for index, slide in enumerate(prs.slides):
        resolved = slide_background_hex(slide)
        background = resolved if resolved is not None else _DEFAULT_BACKGROUND
        ratio = contrast_ratio(clean, background)
        if ratio < MIN_CONTRAST:
            offenders.append(
                {
                    "slide": index,
                    "background": f"#{background}",
                    "contrast": round(ratio, 2),
                    "invisible": ratio <= INVISIBLE_CONTRAST,
                    "assumed": resolved is None,
                }
            )
    return offenders


def contrast_warning(offenders: list[dict], color_hex: str) -> str:
    """One sentence naming the slides and what to do about them."""
    invisible = [o for o in offenders if o["invisible"]]
    slides = ", ".join(str(o["slide"]) for o in offenders)
    colour = color_hex.lstrip("#").upper()
    # Say so when the background was inherited rather than read off the slide,
    # so a caller using a themed master knows why they are being warned.
    basis = (
        " (those slides inherit the template background, taken as white)"
        if all(o.get("assumed") for o in offenders)
        else ""
    )
    if invisible:
        return (
            f"Text set to #{colour} is effectively invisible on slide(s) {slides}{basis} -- "
            f"it nearly matches the background there. Use set_background on those slides, "
            f"or pick a colour that contrasts with them."
        )
    return (
        f"Text set to #{colour} falls below the {MIN_CONTRAST}:1 readable contrast ratio on "
        f"slide(s) {slides}{basis}. Use set_background on those slides, "
        f"or pick a darker or lighter colour."
    )


def fit_to_slide(
    prs,
    left: float,
    top: float,
    width: float,
    height: float,
    margin: float = 0.2,
) -> tuple[float, float, float, float, str]:
    """Clamp a shape's inch-based box so it stays on the canvas.

    Returns (left, top, width, height, note). `note` is empty when the box
    already fitted; otherwise it describes what was moved or shrunk, so the
    caller can surface it instead of silently drawing off the edge.
    """
    slide_w = prs.slide_width / 914400  # EMU per inch
    slide_h = prs.slide_height / 914400

    original = (left, top, width, height)

    # A box larger than the canvas is shrunk first, then pulled back inside it.
    width = max(0.5, min(width, slide_w - 2 * margin))
    height = max(0.5, min(height, slide_h - 2 * margin))
    left = max(margin, min(left, slide_w - width - margin))
    top = max(margin, min(top, slide_h - height - margin))

    if (round(left, 3), round(top, 3), round(width, 3), round(height, 3)) == tuple(round(v, 3) for v in original):
        return left, top, width, height, ""

    note = (
        f"Requested box {original[2]:.2f}x{original[3]:.2f}in at "
        f"({original[0]:.2f}, {original[1]:.2f}) extended past the "
        f"{slide_w:.2f}x{slide_h:.2f}in slide; fitted to {width:.2f}x{height:.2f}in "
        f"at ({left:.2f}, {top:.2f})."
    )
    return left, top, width, height, note
