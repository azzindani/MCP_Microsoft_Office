"""A remote server reads and writes only inside the folders it serves.

Two defects in one resolver. Every tool resolved its path with
`Path(s).resolve()`, so any authenticated caller of the deployed server could
name any file in the container -- only a .docx/.xlsx/.pptx extension check
stood in the way. And the caller's string went through `os.path.expandvars`
first: `"$HOME/nonexistent_probe.docx"` came back from the live endpoint as
"File not found: /home/app/nonexistent_probe.docx", so a path naming a
variable that holds a secret would have echoed the secret the same way.

With MCP_CONFINE_PATHS on (the default for every HTTP deployment) a path must
lie inside MCP_OUTPUT_DIR, the workspace root, or MCP_ALLOWED_ROOTS, judged
after symlinks resolve, and is never expanded against the server's
environment. Template and image paths, which bypassed the resolver, now go
through it. A local stdio install is unchanged, and a workspace name is always
a name.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from docx_basic import engine as dbe  # type: ignore[reportMissingImports]
from shared.file_utils import PathOutsideRootError, resolve_path  # type: ignore[reportMissingImports]
from shared.workspace_utils import get_workspace_dir, get_workspace_root  # type: ignore[reportMissingImports]

OUTSIDE = "/etc/probe.docx" if os.name != "nt" else "C:/Windows/probe.docx"


@pytest.fixture
def served(tmp_path, monkeypatch):
    data = tmp_path / "data"
    ws = tmp_path / "ws"
    data.mkdir()
    ws.mkdir()
    monkeypatch.setenv("MCP_CONFINE_PATHS", "1")
    monkeypatch.setenv("MCP_OUTPUT_DIR", str(data))
    monkeypatch.setenv("MCP_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("MCP_DATA_ROOT", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_ROOTS", raising=False)
    return data


class TestConfined:
    def test_a_file_outside_is_refused(self, served):
        with pytest.raises(PathOutsideRootError, match="outside the folders"):
            resolve_path(OUTSIDE)

    def test_a_relative_path_is_read_from_the_data_folder(self, served):
        assert resolve_path("sub/report.docx") == (served / "sub" / "report.docx").resolve()

    def test_climbing_out_is_refused(self, served):
        with pytest.raises(PathOutsideRootError):
            resolve_path("../escape.docx")

    def test_the_server_environment_is_never_expanded(self, served, monkeypatch):
        monkeypatch.setenv("PROBE_SECRET", "s3cr3t-value")
        path = resolve_path("$PROBE_SECRET/x.docx")
        assert "s3cr3t-value" not in str(path)
        assert path == (served / "$PROBE_SECRET" / "x.docx").resolve()

    def test_a_symlink_is_judged_by_where_it_leads(self, served, tmp_path):
        outside = tmp_path / "outside.docx"
        outside.write_bytes(b"x")
        link = served / "innocent.docx"
        try:
            link.symlink_to(outside)
        except OSError, NotImplementedError:
            pytest.skip("cannot create a symlink here")
        with pytest.raises(PathOutsideRootError):
            resolve_path(str(link))

    def test_an_extra_root_can_be_served(self, served, tmp_path, monkeypatch):
        extra = tmp_path / "extra"
        extra.mkdir()
        monkeypatch.setenv("MCP_ALLOWED_ROOTS", str(extra))
        assert resolve_path(str(extra / "x.docx")) == (extra / "x.docx").resolve()

    def test_a_workspace_base_dir_outside_is_refused(self, served, tmp_path):
        with pytest.raises(PathOutsideRootError, match="base_dir"):
            get_workspace_root(str(tmp_path / "elsewhere"))

    def test_the_tool_refuses(self, served):
        r = dbe.get_document_outline(OUTSIDE)
        assert r["success"] is False
        assert "outside the folders" in r["error"]


class TestLocal:
    def test_a_local_install_is_not_confined(self, monkeypatch):
        monkeypatch.delenv("MCP_CONFINE_PATHS", raising=False)
        assert resolve_path(OUTSIDE) == Path(OUTSIDE).resolve()

    def test_a_local_install_still_expands_variables(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MCP_CONFINE_PATHS", raising=False)
        monkeypatch.setenv("PROBE_DIR", str(tmp_path))
        assert resolve_path("$PROBE_DIR/x.docx") == (tmp_path / "x.docx").resolve()

    @pytest.mark.parametrize("name", ["../../etc", "..", "a/../../b"])
    def test_a_workspace_name_is_always_a_name(self, tmp_path, monkeypatch, name):
        monkeypatch.delenv("MCP_CONFINE_PATHS", raising=False)
        monkeypatch.setenv("MCP_WORKSPACE_DIR", str(tmp_path))
        with pytest.raises(ValueError, match="not a plain name"):
            get_workspace_dir(name)


class TestOutputsConfined:
    """Where a tool WRITES is held to the served folders too.

    A5-sec confined resolve_path, which every INPUT goes through, and missed
    platform_utils.resolve_output_path, the one choke point for all 27 output
    paths: an absolute output_path was used as given and a relative one with a
    folder resolved from the container's working directory. So a confined server
    still created documents wherever a caller pointed it. Found by reading the
    output resolver during a direct sweep of the deployed fleet.
    """

    @pytest.mark.parametrize(
        ("module", "func", "suffix"),
        [
            ("docx_new.engine", "create_document", ".docx"),
            ("xlsx_new.engine", "create_workbook", ".xlsx"),
            ("pptx_new.engine", "create_presentation", ".pptx"),
        ],
    )
    def test_a_creator_refuses_an_outside_output(self, served, tmp_path, module, func, suffix):
        import importlib

        target = tmp_path / "elsewhere" / f"planted{suffix}"
        r = getattr(importlib.import_module(module), func)(str(target), open_after=False)
        assert r["success"] is False, r
        assert "outside the folders" in r["error"]
        assert not target.parent.exists(), "a refused output must leave nothing behind"

    def test_a_relative_output_is_written_into_the_data_folder(self, served):
        from docx_new import engine as dne  # type: ignore[reportMissingImports]

        r = dne.create_document("reports/q3.docx", open_after=False)
        assert r["success"] is True, r
        assert (served / "reports" / "q3.docx").exists()
