"""PPTX Basic MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from pptx_basic import engine

mcp = FastMCP("pptx-basic")


@mcp.tool()
def read_presentation(file_path: str) -> dict:
    """Read presentation index: slides, layouts, and structure."""
    return engine.read_presentation(file_path)


@mcp.tool()
def read_slide(file_path: str, slide_index: int) -> dict:
    """Read all shapes on one slide with name, type, and text."""
    return engine.read_slide(file_path, slide_index)


@mcp.tool()
def search_slides(file_path: str, query: str) -> dict:
    """Search all slides for query text, return matching shapes."""
    return engine.search_slides(file_path, query)


@mcp.tool()
def read_slide_text(file_path: str, slide_index: int) -> dict:
    """Return text of all shapes on one slide (no formatting)."""
    return engine.read_slide_text(file_path, slide_index)


@mcp.tool()
def set_text(
    file_path: str, slide_index: int, shape_name: str, new_text: str
) -> dict:
    """Replace shape text using run-level editing."""
    return engine.set_text(file_path, slide_index, shape_name, new_text)


@mcp.tool()
def add_slide(
    file_path: str, layout_name: str, title: str = "", body: str = ""
) -> dict:
    """Append a slide with given layout, title, and body text."""
    return engine.add_slide(file_path, layout_name, title, body)


@mcp.tool()
def delete_slide(file_path: str, slide_index: int) -> dict:
    """Remove a slide by index."""
    return engine.delete_slide(file_path, slide_index)


@mcp.tool()
def reorder_slide(file_path: str, from_index: int, to_index: int) -> dict:
    """Move a slide from one position to another."""
    return engine.reorder_slide(file_path, from_index, to_index)


@mcp.tool()
def add_text_box(
    file_path: str,
    slide_index: int,
    text: str,
    left: float = 1.0,
    top: float = 1.0,
    width: float = 5.0,
    height: float = 1.0,
) -> dict:
    """Add a text box to a slide at given position in inches."""
    return engine.add_text_box(
        file_path, slide_index, text, left, top, width, height
    )


@mcp.tool()
def diff_versions(
    file_path: str, timestamp_a: str, timestamp_b: str = "current"
) -> dict:
    """Compare two presentation versions by snapshot timestamp."""
    return engine.diff_versions(file_path, timestamp_a, timestamp_b)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
