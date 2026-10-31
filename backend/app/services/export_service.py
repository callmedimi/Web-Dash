"""Unified Export Service (Target Architecture §3 & Phase 5 Step 5.13).

Provides robust, multi-format data export capabilities:
- CSV: UTF-8-SIG encoded (Excel-compatible BOM) with automatic field inference and quoting
- Streaming CSV: Generator-based streaming for large datasets without full memory buffering
- XLSX: Multi-tab styled spreadsheets using openpyxl with formatted headers and auto column widths
- JSON: Extended serializer supporting datetimes, UUIDs, decimals, and sets
"""
import csv
import io
import json
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Optional, Iterable, Iterator, Union


class ExtendedJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder handling datetime, date, UUID, Decimal, and set."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        return super().default(obj)


class UnifiedExportService:
    """Unified service for formatting and streaming tabular or nested data into CSV, XLSX, and JSON."""

    @staticmethod
    def export_csv(
        data: List[Dict[str, Any]],
        fieldnames: Optional[List[str]] = None,
        delimiter: str = ",",
    ) -> bytes:
        """
        Export a list of dictionaries into UTF-8-SIG CSV bytes.
        UTF-8-SIG (b"\\xef\\xbb\\xbf") ensures proper display of Persian, Arabic, and Unicode in Microsoft Excel.
        """
        if not data and not fieldnames:
            return b"\xef\xbb\xbf"

        if fieldnames is None:
            # Infer fieldnames from the union of all keys preserving first-seen order
            seen_fields = []
            for row in data:
                for k in row.keys():
                    if k not in seen_fields:
                        seen_fields.append(k)
            fieldnames = seen_fields

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            delimiter=delimiter,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()

        for row in data:
            sanitized_row = {}
            for col in fieldnames:
                val = row.get(col)
                if val is None:
                    sanitized_row[col] = ""
                elif isinstance(val, (datetime, date)):
                    sanitized_row[col] = val.isoformat()
                elif isinstance(val, (dict, list)):
                    sanitized_row[col] = json.dumps(val, cls=ExtendedJSONEncoder)
                else:
                    sanitized_row[col] = str(val)
            writer.writerow(sanitized_row)

        return output.getvalue().encode("utf-8-sig")

    @staticmethod
    def stream_csv(
        rows_iterable: Iterable[Dict[str, Any]],
        fieldnames: Optional[List[str]] = None,
        delimiter: str = ",",
    ) -> Iterator[bytes]:
        """
        Yield CSV byte chunks row by row, prepending UTF-8-SIG BOM on the first chunk.
        Suitable for streaming large database query results via Flask Response.
        """
        # Yield UTF-8-SIG BOM first
        yield b"\xef\xbb\xbf"

        iterator = iter(rows_iterable)
        first_row = None

        if fieldnames is None:
            try:
                first_row = next(iterator)
                fieldnames = list(first_row.keys())
            except StopIteration:
                return

        # Write header
        hdr_out = io.StringIO()
        writer = csv.DictWriter(hdr_out, fieldnames=fieldnames, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        yield hdr_out.getvalue().encode("utf-8")

        def _format_row(row_dict: Dict[str, Any]) -> bytes:
            row_out = io.StringIO()
            w = csv.DictWriter(row_out, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
            sanitized = {}
            for col in fieldnames:
                v = row_dict.get(col)
                if v is None:
                    sanitized[col] = ""
                elif isinstance(v, (datetime, date)):
                    sanitized[col] = v.isoformat()
                elif isinstance(v, (dict, list)):
                    sanitized[col] = json.dumps(v, cls=ExtendedJSONEncoder)
                else:
                    sanitized[col] = str(v)
            w.writerow(sanitized)
            return row_out.getvalue().encode("utf-8")

        if first_row is not None:
            yield _format_row(first_row)

        for row in iterator:
            yield _format_row(row)

    @staticmethod
    def export_xlsx(
        sheets: Union[Dict[str, Any], List[Dict[str, Any]]],
        default_title: str = "Export",
    ) -> bytes:
        """
        Export tabular data into a styled multi-sheet or single-sheet Excel workbook using openpyxl.
        'sheets' can be:
          - A list of row dicts: creates a single sheet named default_title
          - A dictionary of sheet_name -> list of row dicts (or dict with 'columns' and 'rows')
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        # Remove default empty sheet later or use it as first sheet
        default_sheet = wb.active

        # Style definitions
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        cell_font = Font(name="Calibri", size=10)
        border = Border(
            left=Side(style="thin", color="E0E0E0"),
            right=Side(style="thin", color="E0E0E0"),
            top=Side(style="thin", color="E0E0E0"),
            bottom=Side(style="thin", color="E0E0E0"),
        )

        sheet_dict: Dict[str, Any] = {}
        if isinstance(sheets, list):
            sheet_dict[default_title] = sheets
        elif isinstance(sheets, dict):
            sheet_dict = sheets
        else:
            sheet_dict[default_title] = []

        is_first = True
        for sheet_name, sheet_content in sheet_dict.items():
            if is_first:
                ws = default_sheet
                ws.title = sheet_name[:31]  # Excel max sheet title is 31 chars
                is_first = False
            else:
                ws = wb.create_sheet(title=sheet_name[:31])

            # Determine columns and rows
            cols: List[str] = []
            rows: List[List[Any]] = []

            if isinstance(sheet_content, list):
                if sheet_content and isinstance(sheet_content[0], dict):
                    # List of dicts
                    cols = list(sheet_content[0].keys())
                    for r in sheet_content:
                        row_vals = []
                        for c in cols:
                            val = r.get(c)
                            if isinstance(val, (datetime, date)):
                                row_vals.append(val.isoformat())
                            elif isinstance(val, (dict, list)):
                                row_vals.append(json.dumps(val, cls=ExtendedJSONEncoder))
                            else:
                                row_vals.append(val if val is not None else "")
                        rows.append(row_vals)
                elif sheet_content and isinstance(sheet_content[0], (list, tuple)):
                    # List of lists
                    rows = [list(r) for r in sheet_content]
            elif isinstance(sheet_content, dict):
                cols = sheet_content.get("columns", [])
                raw_rows = sheet_content.get("rows", [])
                if raw_rows and isinstance(raw_rows[0], dict):
                    for r in raw_rows:
                        row_vals = [r.get(c, "") for c in cols]
                        rows.append(row_vals)
                else:
                    rows = [list(r) for r in raw_rows]

            # Write header if columns exist
            start_row = 1
            if cols:
                ws.append(cols)
                for col_idx in range(1, len(cols) + 1):
                    cell = ws.cell(row=1, column=col_idx)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.border = border
                start_row = 2

            # Write rows
            for row in rows:
                ws.append(row)
                row_idx = ws.max_row
                for col_idx in range(1, len(row) + 1):
                    c_cell = ws.cell(row=row_idx, column=col_idx)
                    c_cell.font = cell_font
                    c_cell.border = border

            # Auto-adjust column widths
            for col in ws.columns:
                max_len = 0
                for cell in col:
                    val_str = str(cell.value or "")
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    @staticmethod
    def export_json(data: Any, indent: int = 2) -> bytes:
        """Export data structure into UTF-8 formatted JSON bytes."""
        text = json.dumps(data, indent=indent, cls=ExtendedJSONEncoder, ensure_ascii=False)
        return text.encode("utf-8")
