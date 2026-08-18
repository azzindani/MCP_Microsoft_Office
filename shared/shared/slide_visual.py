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

    Only an explicitly set solid fill is reported. A slide that takes its
    background from the layout or master is left as None rather than guessed at,
    because a wrong guess would produce a false warning about text the user can
    actually read.
    """
    # Imported here rather than at module scope: shared/ is also imported by the
    # docx and xlsx servers, which have no reason to pull in python-pptx.
    from pptx.enum.dml import MSO_FILL

    try:
        fill = slide.background.fill
        # An untouched slide reports MSO_FILL_TYPE.BACKGROUND, which is exactly
        # the inherit case this returns None for.
        if fill.type == MSO_FILL.SOLID:
            return str(fill.fore_color.rgb)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def unreadable_slides(prs, color_hex: str) -> list[dict]:
    """Return the slides where `color_hex` text would be hard or impossible to read.

    A slide is only reported when its background was set explicitly -- see
    slide_background_hex -- so this cannot fire on a deck using the default
    template.
    """
    clean = color_hex.lstrip("#").upper()
    offenders: list[dict] = []
    for index, slide in enumerate(prs.slides):
        background = slide_background_hex(slide)
        if background is None:
            continue
        ratio = contrast_ratio(clean, background)
        if ratio < MIN_CONTRAST:
            offenders.append(
                {
                    "slide": index,
                    "background": f"#{background}",
                    "contrast": round(ratio, 2),
                    "invisible": ratio <= INVISIBLE_CONTRAST,
                }
            )
    return offenders


def contrast_warning(offenders: list[dict], color_hex: str) -> str:
    """One sentence naming the slides and what to do about them."""
    invisible = [o for o in offenders if o["invisible"]]
    slides = ", ".join(str(o["slide"]) for o in offenders)
    if invisible:
        return (
            f"Text set to #{color_hex.lstrip('#').upper()} is effectively invisible on "
            f"slide(s) {slides} -- it nearly matches the background there. "
            f"Use set_background on those slides, or pick a colour that contrasts with them."
        )
    return (
        f"Text set to #{color_hex.lstrip('#').upper()} falls below the {MIN_CONTRAST}:1 readable "
        f"contrast ratio on slide(s) {slides}. Use set_background on those slides, "
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
