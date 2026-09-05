#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MCP_Microsoft_Office — remote smoke test, all 96 tools across 11 sub-servers.
#
# NOT part of pytest / CI (see CLAUDE.md §15 "Remote smoke tests"). Real auth
# enforcement + real handwritten-prompt-style tool calls producing real
# .docx/.xlsx/.pptx files, chaining real outputs (paragraph indices, shape
# names, timestamps) between calls, against the real public domain. This is
# exactly the kind of check that caught the Invalid Host header regression.
#
# Usage:
#   ./remote_smoke_test.sh                          # reads OFFICE_API_KEY from .env
#   OFFICE_API_KEY=sk-... ./remote_smoke_test.sh     # or pass it directly
#   DOMAIN=http://localhost:8830 ./remote_smoke_test.sh   # test a different target
#   CONTAINER=mcp-office ./remote_smoke_test.sh      # override container name
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

DOMAIN="${DOMAIN:-https://office.casava.space}"
CONTAINER="${CONTAINER:-mcp-office}"
# Read the key out of .env without executing it. `source` runs every line of
# the file, so a line that is not a KEY=VALUE assignment is a command; that has
# already turned a stray summary line into a file named after a secret. A plain
# read of one assignment cannot do that.
if [ -z "${OFFICE_API_KEY:-}" ] && [ -f .env ]; then
  OFFICE_API_KEY=$(sed -n 's/^[[:space:]]*OFFICE_API_KEY[[:space:]]*=[[:space:]]*//p' .env | tail -n1 | tr -d '\042\047\r')
fi
KEY="${OFFICE_API_KEY:?Set OFFICE_API_KEY (env var or .env file) before running}"
D=/tmp/remote-smoke-test
DOCX="$D/report.docx"
DOCX_TPL="$D/template.docx"
XLSX="$D/workbook.xlsx"
XLSX_TPL="$D/template.xlsx"
PPTX="$D/deck.pptx"
PPTX_TPL="$D/template.pptx"
IMG="$D/logo.png"
CSV="$D/data.csv"

FAILS=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS+1)); }
ok_json() { echo "$1" | grep -Eq '\\?"success\\?"[[:space:]]*:[[:space:]]*true'; }

echo "Target: $DOMAIN"

# Tools called without an explicit output_path now default into
# MCP_OUTPUT_DIR, which on a real deployment is a directory the operator
# actually looks at. Remember what was there so the run can leave it exactly
# as it found it (see the cleanup at the very bottom).
SHARED_DIR=$(docker exec "$CONTAINER" printenv MCP_OUTPUT_DIR 2>/dev/null || true)
SHARED_BEFORE=$(mktemp)
[ -n "$SHARED_DIR" ] && docker exec "$CONTAINER" sh -c "ls -1A '$SHARED_DIR' 2>/dev/null" | sort > "$SHARED_BEFORE"

echo
echo "== seed a real logo image + a real CSV into the container =="
docker exec "$CONTAINER" mkdir -p "$D"
docker exec "$CONTAINER" python3 -c "
from PIL import Image
Image.new('RGB', (40, 20), color=(200, 30, 30)).save('$IMG')
"
docker exec "$CONTAINER" python3 -c "
open('$CSV','w').write('Region,Units,Revenue\nAPAC,120,1450.5\nEMEA,95,1120.2\nAMER,80,990.75\n')
"
pass "real 40x20 PNG logo + real CSV seeded"

declare -A SID
init_session() {
  curl -s -i -X POST "$DOMAIN/$1/mcp" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H "Authorization: Bearer $KEY" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
    | grep -i mcp-session-id | tr -d '\r' | awk '{print $2}'
}
init_notified() {
  curl -s -X POST "$DOMAIN/$1/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H "Authorization: Bearer $KEY" -H "mcp-session-id: $2" \
    -d '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}' > /dev/null
}

echo
echo "== auth enforcement =="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$DOMAIN/docx-basic/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}')
[ "$code" = "401" ] && pass "no token -> 401" || fail "no token -> expected 401, got $code"

for tier in docx-basic docx-tables docx-layout docx-new xlsx-basic xlsx-formulas xlsx-charts xlsx-new pptx-basic pptx-design pptx-new; do
  SID[$tier]=$(init_session "$tier")
  init_notified "$tier" "${SID[$tier]}"
done
[ -n "${SID[docx-basic]}" ] && pass "valid token -> sessions established on all 11 sub-servers" || fail "no session id"

call() {
  local tier="$1" id="$2" name="$3" args="$4"
  curl -s -X POST "$DOMAIN/$tier/mcp" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H "Authorization: Bearer $KEY" -H "mcp-session-id: ${SID[$tier]}" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":$id,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":$args}}"
}
extract() {
  echo "$1" | grep -oE "\\\\?\"$2\\\\?\"[[:space:]]*:[[:space:]]*\\\\?\"[^\\\\\"]*" | head -1 | sed -E 's/.*"([^"]*)$/\1/'
}
# A tool's document arrives as the JSON *string* result.content[0].text, so its
# keys come through escaped: \"block_count\": 4. This pattern matched only the
# unescaped shape, so it returned nothing on every real response. It had no
# callers when that was found, which is why nothing had noticed -- the same
# defect the escaped-key rule in CLAUDE.md was written for.
extract_num() {
  echo "$1" | grep -oE "\\\\?\"$2\\\\?\"[[:space:]]*:[[:space:]]*[0-9]+" | head -1 | grep -oE '[0-9]+$'
}

N=10
LAST_R=""
run() {
  local tier="$1" name="$2" args="$3" prompt="$4"
  echo "== prompt: \"$prompt\" -> $name =="
  N=$((N+1))
  LAST_R=$(call "$tier" "$N" "$name" "$args")
  if ok_json "$LAST_R"; then pass "$name succeeded"; else fail "$name -> $LAST_R"; fi
}

echo
echo "===== docx-new (9 tools) ====="
run docx-new list_block_kinds "{}" "what block kinds can I use?"
run docx-new create_document "{\"output_path\":\"$D/blank.docx\"}" "create a blank document"
run docx-new create_from_text "{\"output_path\":\"$DOCX\",\"paragraphs\":[{\"text\":\"Quarterly Report\",\"style\":\"Title\"},{\"text\":\"Revenue grew across all regions this quarter.\",\"style\":\"Normal\"},{\"text\":\"APAC led growth.\",\"style\":\"Normal\"}]}" "create the main report doc"
run docx-new create_from_sections "{\"title\":\"Report Sections\",\"sections\":[{\"heading\":\"Summary\",\"body\":\"Overall performance was strong.\"},{\"heading\":\"Details\",\"body\":\"See appendix for details.\"}],\"output_path\":\"$D/sections.docx\"}" "create a doc with sections"
run docx-new create_from_blocks "{\"title\":\"Executive Brief\",\"blocks\":[{\"kind\":\"callout\",\"title\":\"Bottom line\",\"text\":\"Revenue grew in every region.\"},{\"kind\":\"kpi\",\"items\":[{\"value\":\"1450.5\",\"label\":\"APAC\"}]},{\"kind\":\"table\",\"header\":[\"Region\",\"Revenue\"],\"rows\":[[\"APAC\",\"1450.5\"],[\"EMEA\",\"1120.2\"]]},{\"kind\":\"bullets\",\"items\":[\"Hold pricing.\",\"Watch EMEA.\"]}],\"accent\":\"0B1D3A\",\"output_path\":\"$D/blocks.docx\"}" "build a director-readable brief in one call"
BLOCKS_N=$(extract_num "$LAST_R" block_count || true)
case "$BLOCKS_N" in
  4) pass "create_from_blocks wrote all 4 blocks" ;;
  "") fail "create_from_blocks returned no block_count" ;;
  *) fail "create_from_blocks wrote $BLOCKS_N blocks, expected 4" ;;
esac
# The three new kinds and the brand tokens, over the wire. A block kind can pass
# every unit test and be unreachable because the serving wrapper never forwarded
# the argument; only the deployed HTTP surface shows that.
BRIEF_R=$(call docx-new 200 create_from_blocks "{\"title\":\"Board Paper\",\"blocks\":[{\"kind\":\"risks\",\"items\":[{\"risk\":\"Model may be leaking\",\"level\":\"high\",\"mitigation\":\"Retrain on a time split\"}]},{\"kind\":\"checklist\",\"items\":[{\"text\":\"Drop id\",\"done\":true},{\"text\":\"Re-split\",\"done\":false}]},{\"kind\":\"links\",\"items\":[{\"label\":\"Dashboard\",\"url\":\"https://example.test/dash.html\"}]}],\"accent\":\"0B1D3A\",\"font\":\"Georgia\",\"output_path\":\"$D/board.docx\"}")
LINKS_N=$(extract_num "$BRIEF_R" links_embedded)
case "$LINKS_N" in
  1) pass "risks/checklist/links reached the deployed tool" ;;
  "") fail "new block kinds returned no links_embedded -> $BRIEF_R" ;;
  *) fail "links_embedded was $LINKS_N, expected 1" ;;
esac
if echo "$BRIEF_R" | grep -q 'Georgia'; then pass "brand font applied over the wire"; else fail "font token dropped -> $BRIEF_R"; fi
run docx-new create_letter "{\"from_name\":\"Ops Team\",\"to_name\":\"Finance Team\",\"subject\":\"Q1 Summary\",\"body\":\"Please find the summary attached.\",\"output_path\":\"$D/letter.docx\"}" "create a letter"
run docx-new merge_documents "{\"file_paths\":[\"$DOCX\",\"$D/sections.docx\"],\"output_path\":\"$D/merged.docx\"}" "merge the report and sections docs"
run docx-new create_from_text "{\"output_path\":\"$DOCX_TPL\",\"paragraphs\":[{\"text\":\"Dear {{name}},\",\"style\":\"Normal\"},{\"text\":\"Your balance is {{balance}}.\",\"style\":\"Normal\"}]}" "create a template doc with placeholders"
run docx-new create_from_template "{\"template_path\":\"$DOCX_TPL\",\"substitutions\":{\"name\":\"Alex\",\"balance\":\"\$100\"},\"output_path\":\"$D/from_template.docx\"}" "fill in the template for Alex"
run docx-new batch_create_from_template "{\"template_path\":\"$DOCX_TPL\",\"data_list\":[{\"name\":\"Sam\",\"balance\":\"\$50\"},{\"name\":\"Jo\",\"balance\":\"\$75\"}],\"output_dir\":\"$D/batch\"}" "batch-generate letters for Sam and Jo"

echo
echo "===== docx-basic (15 tools) on the main report doc ====="
run docx-basic get_document_outline "{\"file_path\":\"$DOCX\"}" "what is the outline of the report?"
run docx-basic get_document_index "{\"file_path\":\"$DOCX\"}" "index the report doc"
run docx-basic read_document "{\"file_path\":\"$DOCX\"}" "read the whole report"
run docx-basic read_paragraph "{\"file_path\":\"$DOCX\",\"paragraph_index\":0}" "read paragraph 0"
run docx-basic read_paragraph_range "{\"file_path\":\"$DOCX\",\"start_index\":0,\"end_index\":2}" "read paragraphs 0-2"
run docx-basic search_paragraphs "{\"file_path\":\"$DOCX\",\"query\":\"APAC\"}" "find the paragraph mentioning APAC"
run docx-basic fetch_section "{\"file_path\":\"$DOCX\",\"address\":\"p0\"}" "fetch section p0"
run docx-basic replace_text "{\"file_path\":\"$DOCX\",\"match_text\":\"APAC led growth.\",\"new_text\":\"APAC led growth this quarter.\"}" "reword the APAC sentence"
run docx-basic insert_paragraph "{\"file_path\":\"$DOCX\",\"after_index\":1,\"text\":\"EMEA also performed well.\"}" "add a note about EMEA after paragraph 1"
run docx-basic append_text "{\"file_path\":\"$DOCX\",\"text\":\"End of report.\"}" "append a closing line"
run docx-basic get_history "{\"file_path\":\"$DOCX\"}" "show the version history"
TS_A=$(extract "$LAST_R" timestamp)
run docx-basic read_receipt "{\"file_path\":\"$DOCX\"}" "show the operation receipt log"
run docx-basic delete_paragraph "{\"file_path\":\"$DOCX\",\"paragraph_index\":4}" "delete the last paragraph"
run docx-basic get_history "{\"file_path\":\"$DOCX\"}" "show the version history again"
TS_B=$(extract "$LAST_R" timestamp)
if [ -n "$TS_A" ] && [ -n "$TS_B" ] && [ "$TS_A" != "$TS_B" ]; then
  run docx-basic diff_versions "{\"file_path\":\"$DOCX\",\"timestamp_a\":\"$TS_A\",\"timestamp_b\":\"current\"}" "diff the current version against an earlier snapshot"
  run docx-basic restore_version "{\"file_path\":\"$DOCX\",\"timestamp\":\"$TS_A\"}" "restore the earlier snapshot"
else
  fail "diff_versions/restore_version skipped — could not capture two distinct real timestamps from get_history"
fi

echo
echo "===== docx-tables (10 tools) ====="
run docx-tables add_table "{\"file_path\":\"$DOCX\",\"after_paragraph_index\":0,\"rows\":2,\"cols\":2,\"data\":[[\"Region\",\"Revenue\"],[\"APAC\",\"1450.5\"]]}" "add a 2x2 table after paragraph 0"
run docx-tables list_tables "{\"file_path\":\"$DOCX\"}" "list the tables in the doc"
run docx-tables read_table "{\"file_path\":\"$DOCX\",\"table_index\":0}" "read table 0"
run docx-tables read_table_row "{\"file_path\":\"$DOCX\",\"table_index\":0,\"row\":0}" "read row 0 of table 0"
run docx-tables search_table_cells "{\"file_path\":\"$DOCX\",\"query\":\"APAC\"}" "find APAC in any table cell"
run docx-tables set_cell "{\"file_path\":\"$DOCX\",\"table_index\":0,\"row\":1,\"col\":1,\"text\":\"1500.0\"}" "update the revenue cell"
run docx-tables add_row "{\"file_path\":\"$DOCX\",\"table_index\":0,\"data\":[\"EMEA\",\"1120.2\"]}" "add an EMEA row to the table"
run docx-tables delete_row "{\"file_path\":\"$DOCX\",\"table_index\":0,\"row\":2}" "delete the row I just added"
run docx-tables set_cell_style "{\"file_path\":\"$DOCX\",\"table_index\":0,\"row\":0,\"fill\":\"0B1D3A\",\"color\":\"FFFFFF\",\"bold\":\"true\"}" "shade the table header navy with white text"
run docx-tables set_cell_style "{\"file_path\":\"$DOCX\",\"table_index\":0,\"band_fill\":\"EEEEEE\"}" "stripe the body rows"
BANDED_N=$(extract_num "$LAST_R" rows_banded || true)
[ -n "$BANDED_N" ] || fail "set_cell_style returned no rows_banded"
run docx-tables delete_table "{\"file_path\":\"$DOCX\",\"table_index\":0}" "delete the table entirely"

echo
echo "===== docx-layout (7 tools) ====="
run docx-layout set_heading "{\"file_path\":\"$DOCX\",\"paragraph_index\":0,\"level\":1}" "make paragraph 0 a heading"
run docx-layout set_font "{\"file_path\":\"$DOCX\",\"paragraph_index\":1,\"font_name\":\"Arial\",\"font_size\":12,\"bold\":\"true\",\"color\":\"0B1D3A\",\"line_spacing\":1.15,\"space_after\":6}" "bold navy Arial 12 with a little air under it"
run docx-layout set_paragraph_style "{\"file_path\":\"$DOCX\",\"paragraph_index\":1,\"style_name\":\"Body Text\"}" "set paragraph 1 to Body Text style"
run docx-layout add_image "{\"file_path\":\"$DOCX\",\"paragraph_index\":0,\"image_path\":\"$IMG\",\"width_inches\":1.0}" "insert the logo image after paragraph 0"
run docx-layout set_page_margins "{\"file_path\":\"$DOCX\",\"top\":1.0,\"bottom\":1.0,\"left\":1.0,\"right\":1.0}" "set 1-inch margins"
run docx-layout add_header_footer "{\"file_path\":\"$DOCX\",\"text\":\"Confidential\",\"location\":\"footer\",\"font_size\":8,\"color\":\"595959\",\"align\":\"center\",\"page_numbers\":true}" "add a small grey centred footer that numbers its pages"
run docx-layout export_pdf "{\"file_path\":\"$DOCX\",\"output_path\":\"$D/report.pdf\"}" "export the report to PDF"

echo
echo "===== xlsx-new (6 tools) ====="
run xlsx-new create_workbook "{\"sheet_name\":\"Main\",\"output_path\":\"$D/blank.xlsx\"}" "create a blank workbook"
run xlsx-new create_from_data "{\"sheet_name\":\"Sales\",\"headers\":[\"Region\",\"Units\",\"Revenue\"],\"rows\":[[\"APAC\",120,1450.5],[\"EMEA\",95,1120.2],[\"AMER\",80,990.75]],\"output_path\":\"$XLSX\"}" "create the main sales workbook"
run xlsx-new create_report "{\"title\":\"Q1 Report\",\"sheets\":[{\"name\":\"Summary\",\"headers\":[\"Metric\",\"Value\"],\"rows\":[[\"Total Revenue\",3561.45]]}],\"output_path\":\"$D/report.xlsx\"}" "create a report workbook"
run xlsx-new create_from_data "{\"sheet_name\":\"Main\",\"headers\":[\"Name\",\"Balance\"],\"rows\":[[\"{{name}}\",\"{{balance}}\"]],\"output_path\":\"$XLSX_TPL\"}" "create a template workbook with placeholders"
run xlsx-new create_from_template "{\"template_path\":\"$XLSX_TPL\",\"substitutions\":{\"{{name}}\":\"Alex\",\"{{balance}}\":\"100\"},\"output_path\":\"$D/xlsx_from_template.xlsx\"}" "fill in the workbook template"
run xlsx-new create_from_csv "{\"csv_path\":\"$CSV\",\"sheet_name\":\"Imported\",\"output_path\":\"$D/from_csv.xlsx\"}" "import the CSV into a workbook"
run xlsx-new create_invoice "{\"company_name\":\"Acme Co\",\"client_name\":\"Beta LLC\",\"invoice_number\":\"INV-001\",\"items\":[{\"description\":\"Consulting\",\"quantity\":10,\"unit_price\":100}],\"output_path\":\"$D/invoice.xlsx\"}" "create an invoice"

echo
echo "===== xlsx-basic (14 tools) on the main sales workbook ====="
run xlsx-basic list_sheets "{\"file_path\":\"$XLSX\"}" "what sheets are in the sales workbook?"
run xlsx-basic get_sheet_summary "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\"}" "summarize the Sales sheet"
run xlsx-basic read_cell "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"cell_address\":\"A1\"}" "read cell A1"
run xlsx-basic read_cell_range "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_address\":\"A1:C4\"}" "read the whole table range"
run xlsx-basic search_cells "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"query\":\"APAC\"}" "find APAC in the sheet"
run xlsx-basic set_cell "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"cell_address\":\"C2\",\"value\":\"1500.0\"}" "update APAC revenue"
run xlsx-basic set_range "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"start_cell\":\"A6\",\"data\":[[\"Total\",295,3561.45]]}" "add a totals row"
run xlsx-basic insert_row "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"row_index\":2}" "insert a blank row at row 2"
run xlsx-basic add_sheet "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Notes\"}" "add a Notes sheet"
run xlsx-basic rename_sheet "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Notes\",\"new_name\":\"Remarks\"}" "rename Notes to Remarks"
run xlsx-basic copy_sheet "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"new_name\":\"Sales Copy\"}" "duplicate the Sales sheet"
run xlsx-basic sort_sheet "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales Copy\",\"column\":\"A\",\"has_header\":true}" "sort the Sales Copy sheet by region"
run xlsx-basic find_duplicates "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"column\":\"A\",\"has_header\":true}" "check for duplicate regions"
run xlsx-basic delete_row "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"row_index\":2}" "delete the blank row I inserted"

echo
echo "===== xlsx-formulas (9 tools) ====="
run xlsx-formulas set_formula "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"cell_address\":\"D2\",\"formula\":\"=C2/B2\"}" "add a revenue-per-unit formula"
run xlsx-formulas fill_formula_down "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"formula\":\"=C{row}/B{row}\",\"start_cell\":\"D3\",\"end_row\":4}" "fill that formula down"
run xlsx-formulas auto_sum "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"data_range\":\"C2:C4\",\"sum_cell\":\"C5\"}" "auto-sum the revenue column"
run xlsx-formulas set_named_range "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_name\":\"RevenueRange\",\"range_address\":\"C2:C4\"}" "name the revenue range"
run xlsx-formulas set_conditional_format "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_address\":\"C2:C4\",\"rule\":\"greater_than\",\"value\":1000,\"color\":\"red\"}" "highlight revenue over 1000"
run xlsx-formulas set_data_validation "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_address\":\"A2:A4\",\"validation_type\":\"list\",\"formula1\":\"APAC,EMEA,AMER\"}" "restrict region to a dropdown list"
run xlsx-formulas freeze_panes "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"cell_address\":\"A2\"}" "freeze the header row"
run xlsx-formulas set_autofilter "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_address\":\"A1:D4\"}" "add autofilter to the table"
run xlsx-formulas convert_to_values "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"range_address\":\"D2:D4\"}" "convert the formula column to static values"

echo
echo "===== xlsx-charts (5 tools) ====="
run xlsx-charts add_chart "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"chart_type\":\"bar\",\"data_range\":\"A1:C4\",\"title\":\"Revenue by Region\",\"anchor_cell\":\"F2\"}" "add a bar chart of revenue by region"
run xlsx-charts add_pivot_table "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"source_range\":\"A1:C4\",\"dest_cell\":\"F20\",\"rows\":\"Region\",\"values\":\"Revenue\"}" "add a pivot table of revenue by region and units"
run xlsx-charts set_cell_style "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"cell_address\":\"A1\",\"bold\":\"true\",\"fill_color\":\"DDDDDD\"}" "bold and shade the header cell"
run xlsx-charts update_chart "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"chart_index\":0,\"title\":\"Revenue by Region (updated)\"}" "retitle the chart"
run xlsx-charts delete_chart "{\"file_path\":\"$XLSX\",\"sheet_name\":\"Sales\",\"chart_index\":0}" "delete the chart"

echo
echo "===== pptx-new (6 tools) ====="
run pptx-new create_presentation "{\"title\":\"Q1 Review\",\"subtitle\":\"Company All-Hands\",\"output_path\":\"$D/blank.pptx\"}" "create a blank deck"
run pptx-new create_from_outline "{\"slides\":[{\"title\":\"Welcome\",\"bullets\":[\"Agenda\",\"Goals\"]},{\"title\":\"Revenue\",\"bullets\":[\"APAC up 12%\",\"EMEA steady\"]}],\"output_path\":\"$PPTX\"}" "create the main deck from an outline"
run pptx-new create_deck_from_data "{\"title\":\"Metrics\",\"data_slides\":[{\"title\":\"Revenue by Region\",\"headers\":[\"Region\",\"Revenue\"],\"rows\":[[\"APAC\",1450.5],[\"EMEA\",1120.2]]}],\"output_path\":\"$D/data_deck.pptx\"}" "build a deck from tabular data"
run pptx-new create_agenda "{\"meeting_title\":\"Q1 Review\",\"date\":\"2026-01-15\",\"items\":[{\"topic\":\"Welcome\",\"duration\":\"5 min\",\"owner\":\"Ops Team\"},{\"topic\":\"Revenue Review\",\"duration\":\"15 min\",\"owner\":\"Finance\"},{\"topic\":\"Q&A\",\"duration\":\"10 min\",\"owner\":\"All\"}],\"presenter\":\"Ops Team\",\"output_path\":\"$D/agenda.pptx\"}" "create an agenda deck"
run pptx-new create_from_outline "{\"slides\":[{\"title\":\"{{name}}'s Slide\",\"bullets\":[\"{{note}}\"]}],\"output_path\":\"$PPTX_TPL\"}" "create a template deck with placeholders"
run pptx-new create_from_template "{\"template_path\":\"$PPTX_TPL\",\"substitutions\":{\"Coverage\":\"Filled\"},\"output_path\":\"$D/from_template.pptx\"}" "instantiate the deck template"
run pptx-new create_from_docx "{\"docx_path\":\"$DOCX\",\"max_slides\":5,\"output_path\":\"$D/from_docx.pptx\"}" "turn the report doc into slides"

echo
echo "===== pptx-basic (10 tools) on the main deck ====="
run pptx-basic read_presentation "{\"file_path\":\"$PPTX\"}" "read the whole deck"
run pptx-basic read_slide "{\"file_path\":\"$PPTX\",\"slide_index\":0}" "read slide 0"
SHAPE=$(extract "$LAST_R" shape_name)
[ -z "$SHAPE" ] && SHAPE=$(extract "$LAST_R" name)
run pptx-basic read_slide_text "{\"file_path\":\"$PPTX\",\"slide_index\":0}" "read the text on slide 0"
run pptx-basic search_slides "{\"file_path\":\"$PPTX\",\"query\":\"APAC\"}" "find the slide mentioning APAC"
if [ -n "$SHAPE" ]; then
  run pptx-basic set_text "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"shape_name\":\"$SHAPE\",\"new_text\":\"Welcome (updated)\"}" "retitle slide 0's $SHAPE shape"
else
  fail "set_text skipped — could not capture a real shape_name from read_slide"
fi
run pptx-basic add_slide "{\"file_path\":\"$PPTX\",\"layout_name\":\"Title and Content\",\"title\":\"New Slide\",\"body\":\"Added by the smoke test.\"}" "add a new slide"
run pptx-basic add_text_box "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"text\":\"Draft\",\"left\":1.0,\"top\":1.0,\"width\":2.0,\"height\":0.5}" "add a Draft text box to slide 0"
run pptx-basic reorder_slide "{\"file_path\":\"$PPTX\",\"from_index\":2,\"to_index\":0}" "move the new slide to the front"
echo "== prompt: \"diff the deck against itself\" -> diff_versions =="
N=$((N+1))
PROBE_R=$(call pptx-basic "$N" diff_versions "{\"file_path\":\"$PPTX\",\"timestamp_a\":\"__probe__\",\"timestamp_b\":\"current\"}")
REAL_TS=$(echo "$PROBE_R" | grep -oE "'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9-]+Z'" | head -1 | tr -d "'")
if [ -n "$REAL_TS" ]; then
  run pptx-basic diff_versions "{\"file_path\":\"$PPTX\",\"timestamp_a\":\"$REAL_TS\",\"timestamp_b\":\"current\"}" "diff the deck against a real earlier snapshot ($REAL_TS)"
else
  fail "diff_versions -> could not extract a real snapshot timestamp from the probe error"
fi
run pptx-basic delete_slide "{\"file_path\":\"$PPTX\",\"slide_index\":0}" "delete the slide I just moved to the front"

echo
echo "===== pptx-design (8 tools) ====="
run pptx-design set_background "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"color_hex\":\"F0F0F0\"}" "set slide 0's background to light gray"
if [ -n "$SHAPE" ]; then
  run pptx-design set_font_style "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"shape_name\":\"$SHAPE\",\"font_name\":\"Arial\",\"font_size\":32,\"bold\":\"true\"}" "make slide 0's title bold Arial"

  # bold is a TRI-STATE STRING, not a boolean, and this is where that gets
  # proved end to end. Round 22 found set_font_all_slides(bold=false) answering
  # success:true, shapes_modified:6, bold:false with the title still bold --
  # `if bold:` cannot tell "make this not bold" from "bold was not mentioned".
  # The schema is now str: "" leaves, "true" sets, "false" clears.
  #
  # The three calls in this script passed a JSON boolean until now, which the
  # new schema refuses outright -- so the smoke test was still requiring the
  # defect, and that is why abb5e94's CI went red here.
  echo "== prompt: \"take the bold off slide 0's title\" -> set_font_style(bold=false) =="
  N=$((N+1))
  OFF_R=$(call pptx-design "$N" set_font_style "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"shape_name\":\"$SHAPE\",\"bold\":\"false\"}")
  if ok_json "$OFF_R" && echo "$OFF_R" | grep -Eq '\\?"bold\\?"[[:space:]]*:[[:space:]]*\\?"false'; then
    pass "bold=false is applied and reported as applied"
  else
    fail "set_font_style(bold=false) -> $OFF_R"
  fi

  echo "== a JSON boolean is refused, loudly, rather than silently ignored =="
  N=$((N+1))
  BOOL_R=$(call pptx-design "$N" set_font_style "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"shape_name\":\"$SHAPE\",\"bold\":true}")
  if ok_json "$BOOL_R"; then
    fail "a JSON boolean was accepted for bold — the old silent-ignore path is back"
  else
    pass "a JSON boolean is rejected instead of accepted-and-ignored"
  fi
else
  fail "set_font_style skipped — no real shape_name captured"
fi
run pptx-design add_table "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"rows\":2,\"cols\":2,\"data\":[[\"Region\",\"Revenue\"],[\"APAC\",\"1450.5\"]]}" "add a table to slide 0"
run pptx-design add_chart "{\"file_path\":\"$PPTX\",\"slide_index\":0,\"chart_type\":\"bar\",\"data\":{\"categories\":[\"APAC\",\"EMEA\"],\"series\":[{\"name\":\"Revenue\",\"values\":[1450.5,1120.2]}]},\"title\":\"Revenue\"}" "add a bar chart to slide 0"
run pptx-design duplicate_slide "{\"file_path\":\"$PPTX\",\"slide_index\":0}" "duplicate slide 0"
run pptx-design add_image_to_all_slides "{\"file_path\":\"$PPTX\",\"image_path\":\"$IMG\",\"left\":0.1,\"top\":0.1,\"width\":0.5,\"height\":0.25}" "add the logo to every slide"
run pptx-design set_font_all_slides "{\"file_path\":\"$PPTX\",\"font_name\":\"Calibri\",\"font_size\":18}" "set the font on every slide to Calibri 18"
run pptx-design export_pdf "{\"file_path\":\"$PPTX\",\"output_path\":\"$D/deck.pdf\"}" "export the deck to PDF"

echo
echo "===== hybrid file exchange (remote-only behaviour) ====="
# Only meaningful against a deployment that sets MCP_OUTPUT_DIR /
# MCP_PUBLIC_BASE_URL — exactly what pytest cannot check, since pytest never
# spins up a server or touches the network.
if [ -z "$SHARED_DIR" ]; then
  echo "  SKIP: MCP_OUTPUT_DIR is unset on $CONTAINER — nothing to verify"
else
  echo "== prompt: \"make me a workbook\" -> create_workbook with no output_path =="
  N=$((N+1))
  EX_R=$(call xlsx-new "$N" create_workbook '{"sheet_name":"Exchange"}')
  EX_PATH=$(extract "$EX_R" output)
  EX_URL=$(extract "$EX_R" public_url)
  case "$EX_PATH" in
    "$SHARED_DIR"/*) pass "default output landed in the shared dir ($EX_PATH)" ;;
    *) fail "default output went to $EX_PATH, expected it under $SHARED_DIR (key: output)" ;;
  esac
  [ -n "$EX_URL" ] && pass "response carried public_url ($EX_URL)" || fail "no public_url in response"
  if docker exec "$CONTAINER" test -s "$EX_PATH"; then
    pass "the workbook is a real non-empty file on disk, not just a success message"
  else
    fail "no file at $EX_PATH inside the container"
  fi
  MODE=$(docker exec "$CONTAINER" stat -c '%a' "$EX_PATH" 2>/dev/null)
  case "$MODE" in
    *[4567]) pass "generated file is readable by the file server sharing the dir (mode $MODE)" ;;
    *) fail "mode $MODE leaves the file unreadable to anything else sharing the directory" ;;
  esac
  docker exec "$CONTAINER" rm -f "$EX_PATH"

  echo "== prompt: \"open the document at <link>\" -> a URL as a file path =="
  # A *sibling* endpoint's public /health, never this server's own: fetching
  # its own public URL deadlocks, because the tool call occupies the worker
  # that would have to serve the request, and the fetch dies on the timeout.
  N=$((N+1))
  URL_R=$(call docx-basic "$N" read_document '{"file_path":"https://math.casava.space/health"}')
  if echo "$URL_R" | grep -q "does not fetch URLs"; then
    echo "  SKIP: MCP_FETCH_URLS is not enabled on $CONTAINER"
  elif echo "$URL_R" | grep -qE 'health\.json|inbox|\.docx'; then
    pass "a URL was accepted as a file path and fetched server-side"
  else
    fail "URL input -> $URL_R"
  fi

  echo "== SSRF guard: a private address must be refused =="
  N=$((N+1))
  SSRF_R=$(call docx-basic "$N" read_document '{"file_path":"http://169.254.169.254/latest/meta-data/"}')
  if echo "$SSRF_R" | grep -q "non-public address"; then
    pass "link-local metadata address refused"
  elif echo "$SSRF_R" | grep -q "does not fetch URLs"; then
    echo "  SKIP: URL fetching disabled, guard not reachable"
  else
    fail "SSRF guard did not fire -> $SSRF_R"
  fi
fi

if [ -n "$SHARED_DIR" ]; then
  echo
  echo "== leave the shared directory as we found it =="
  docker exec "$CONTAINER" sh -c "ls -1A '$SHARED_DIR' 2>/dev/null" | sort \
    | comm -13 "$SHARED_BEFORE" - \
    | while IFS= read -r leftover; do
        [ -n "$leftover" ] && docker exec "$CONTAINER" rm -rf "$SHARED_DIR/$leftover"
      done
  pass "removed everything this run added to $SHARED_DIR"
fi
rm -f "$SHARED_BEFORE"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "ALL 96 TOOLS PASSED against $DOMAIN"
else
  echo "$FAILS TOOL(S) FAILED against $DOMAIN"
  exit 1
fi
