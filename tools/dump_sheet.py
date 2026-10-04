"""Print an SFI sheet as `row: label | values...` for building extractors.
usage: python tools/dump_sheet.py FILE SHEET [max_rows]"""
import sys, openpyxl
f, sheet = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 200
ws = openpyxl.load_workbook(f, read_only=True, data_only=True)[sheet]
for i, r in enumerate(ws.iter_rows(max_row=n, values_only=True), 1):
    cells = [c for c in r if c is not None and str(c).strip() != ""]
    if not cells:
        continue
    lab = [str(c).strip()[:45] for c in cells if isinstance(c, str)]
    nums = [round(c, 3) if isinstance(c, float) else c for c in cells if isinstance(c, (int, float))]
    print(f"{i:3}: {' / '.join(lab)[:70]:70} | {nums[:9]}")
