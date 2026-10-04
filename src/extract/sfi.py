"""Generic helpers for reading bank SFI Excel packages.

Page numbers move between years, so tables are located by their title text
and rows by their label, never by position.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

QUARTER_RE = re.compile(r"^\s*Q([1-4])\s*[/\- ]?\s*(?:F|FY)?(\d{2}|\d{4})\s*$", re.I)


@dataclass
class Row:
    idx: int
    label: str
    values: dict  # (fiscal_year, fiscal_quarter) -> float


@dataclass
class Sheet:
    name: str
    text: str  # upper-cased text of the first rows, for locating tables
    rows: list[Row]


def clean_label(s: str) -> str:
    s = re.sub(r"_x000D_", " ", s)
    s = re.sub(r"\s+\d+(,\s*\d+)*\s*$", "", s.strip())  # trailing footnote markers
    s = re.sub(r"\(\d\)$", "", s).strip()
    return re.sub(r"\s+", " ", s)


def _quarter(cell) -> tuple[int, int] | None:
    if not isinstance(cell, str):
        return None
    m = QUARTER_RE.match(cell)
    if not m:
        return None
    y = int(m.group(2))
    return (2000 + y if y < 100 else y, int(m.group(1)))


def read_sheet(ws, max_rows: int = 250, label_cols: int = 5) -> Sheet:
    raw = list(ws.iter_rows(max_row=max_rows, values_only=True))
    colmap = {}
    for r in raw[:15]:
        qs = {j: _quarter(c) for j, c in enumerate(r)}
        qs = {j: q for j, q in qs.items() if q}
        if len(qs) >= 3:
            colmap = {}
            for j, q in qs.items():
                colmap.setdefault(q, j)  # first occurrence of each quarter wins
            colmap = {j: q for q, j in colmap.items()}
            break
    rows = []
    for i, r in enumerate(raw, 1):
        label = next((c for c in r[:label_cols] if isinstance(c, str) and c.strip()), None)
        if label is None:
            label = ""
        vals = {q: float(r[j]) for j, q in colmap.items()
                if j < len(r) and isinstance(r[j], (int, float)) and not isinstance(r[j], bool)}
        rows.append(Row(i, clean_label(label), vals))
    head = " ".join(str(c) for r in raw[:6] for c in r if isinstance(c, str))
    return Sheet(ws.title, head.upper(), rows)


def load(path: Path) -> list[Sheet]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [read_sheet(ws) for ws in wb.worksheets]


def find_sheets(sheets: list[Sheet], *must: str, anywhere: bool = False) -> list[Sheet]:
    """Sheets whose title area (or, with anywhere=True, any label) contains all strings."""
    out = []
    for s in sheets:
        hay = s.text if not anywhere else s.text + " " + " ".join(r.label.upper() for r in s.rows)
        if all(m.upper() in hay for m in must):
            out.append(s)
    return out


def find_row(sheet: Sheet, pattern: str, start: int = 0, end: int | None = None,
             with_values: bool = True) -> Row | None:
    rx = re.compile(pattern, re.I)
    for r in sheet.rows:
        if r.idx < start or (end is not None and r.idx > end):
            continue
        if rx.search(r.label) and (r.values or not with_values):
            return r
    return None


def section(sheet: Sheet, start_pattern: str, end_pattern: str, after: int = 0) -> list[Row]:
    """Rows strictly between the first label matching start_pattern (after row `after`)
    and the next label matching end_pattern."""
    start_rx, end_rx = re.compile(start_pattern, re.I), re.compile(end_pattern, re.I)
    out, inside = [], False
    for r in sheet.rows:
        if r.idx <= after:
            continue
        if not inside:
            if start_rx.search(r.label):
                inside = True
            continue
        if end_rx.search(r.label):
            break
        out.append(r)
    return out
