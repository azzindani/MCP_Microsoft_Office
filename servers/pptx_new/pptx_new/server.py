"""PPTX New MCP server — create PowerPoint presentations from scratch."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from pptx_new import engine

mcp = FastMCP("pptx-new")


@mcp.tool()
def create_presentation(
    output_path: str,
    title: str = "",
    subtitle: str = "",
) -> dict:
    """Create a blank PowerPoint with a title slide."""
    return engine.create_presentation(output_path, title, subtitle, open_after=True)


@mcp.tool()
def create_from_outline(
    output_path: str,
    slides: list[dict],
) -> dict:
    """Create .pptx from [{title, content, layout}] slide list."""
    return engine.create_from_outline(output_path, slides, open_after=True)


@mcp.tool()
def create_deck_from_data(
    output_path: str,
    title: str,
    data_slides: list[dict],
) -> dict:
    """Create .pptx deck from title + [{heading, bullets}] list."""
    return engine.create_deck_from_data(output_path, title, data_slides, open_after=True)


@mcp.tool()
def create_from_template(
    template_path: str,
    output_path: str,
) -> dict:
    """Copy .pptx template to output_path as starting point."""
    return engine.create_from_template(template_path, output_path, open_after=True)


@mcp.tool()
def create_agenda(
    output_path: str,
    meeting_title: str,
    date: str,
    items: list,
    presenter: str = "",
) -> dict:
    """Create a meeting agenda .pptx from a list of {topic,duration,owner} items."""
    return engine.create_agenda(output_path, meeting_title, date, items, presenter, open_after=True)


@mcp.tool()
def create_from_docx(
    docx_path: str,
    output_path: str,
    max_slides: int = 20,
) -> dict:
    """Convert a Word document outline into a PowerPoint presentation."""
    return engine.create_from_docx(docx_path, output_path, max_slides, open_after=True)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
