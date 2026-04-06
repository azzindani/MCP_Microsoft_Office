"""DOCX New MCP server — create Word documents from scratch."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from docx_new import engine

mcp = FastMCP("docx-new")


@mcp.tool()
def create_document(output_path: str, open_after: bool = True) -> dict:
    """Create a blank Word document and save to output_path."""
    return engine.create_document(output_path, open_after)


@mcp.tool()
def create_from_text(
    output_path: str,
    paragraphs: list[dict],
    open_after: bool = True,
) -> dict:
    """Create .docx from list of {text, style} paragraph dicts."""
    return engine.create_from_text(output_path, paragraphs, open_after)


@mcp.tool()
def create_from_sections(
    output_path: str,
    title: str,
    sections: list[dict],
    open_after: bool = True,
) -> dict:
    """Create structured .docx from title + [{heading, body}] sections."""
    return engine.create_from_sections(output_path, title, sections, open_after)


@mcp.tool()
def create_from_template(
    template_path: str,
    output_path: str,
    substitutions: dict,
    open_after: bool = True,
) -> dict:
    """Copy template .docx, fill {key: value} substitutions, save."""
    return engine.create_from_template(
        template_path, output_path, substitutions, open_after
    )


@mcp.tool()
def create_letter(
    output_path: str,
    from_name: str,
    to_name: str,
    subject: str,
    body: str,
    open_after: bool = True,
) -> dict:
    """Create a formatted business letter .docx."""
    return engine.create_letter(
        output_path, from_name, to_name, subject, body, open_after
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
