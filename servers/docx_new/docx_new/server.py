"""DOCX New MCP server — create Word documents from scratch."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from docx_new import engine

mcp = FastMCP("docx-new")


@mcp.tool()
def create_document(output_path: str = "") -> dict:
    """Create a blank Word document and save to output_path."""
    return engine.create_document(output_path, open_after=False)


@mcp.tool()
def create_from_text(
    paragraphs: list[dict],
    output_path: str = "",
) -> dict:
    """Create .docx from list of {text, style} paragraph dicts."""
    return engine.create_from_text(output_path, paragraphs, open_after=True)


@mcp.tool()
def create_from_sections(
    title: str,
    sections: list[dict],
    output_path: str = "",
) -> dict:
    """Create structured .docx from title + [{heading, body}] sections."""
    return engine.create_from_sections(output_path, title, sections, open_after=True)


@mcp.tool()
def create_from_template(
    template_path: str,
    substitutions: dict,
    output_path: str = "",
) -> dict:
    """Copy template .docx, fill {key: value} substitutions, save."""
    return engine.create_from_template(template_path, output_path, substitutions, open_after=True)


@mcp.tool()
def create_letter(
    from_name: str,
    to_name: str,
    subject: str,
    body: str,
    output_path: str = "",
) -> dict:
    """Create a formatted business letter .docx."""
    return engine.create_letter(output_path, from_name, to_name, subject, body, open_after=True)


@mcp.tool()
def merge_documents(
    file_paths: list,
    output_path: str = "",
    add_page_break: bool = True,
) -> dict:
    """Merge multiple .docx files into one document."""
    return engine.merge_documents(file_paths, output_path, add_page_break, open_after=True)


@mcp.tool()
def batch_create_from_template(
    template_path: str,
    data_list: list,
    output_dir: str,
    filename_key: str = "",
) -> dict:
    """Generate N .docx files from a template + list of {key:value} dicts."""
    return engine.batch_create_from_template(
        template_path, data_list, output_dir, filename_key, open_after=True
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
