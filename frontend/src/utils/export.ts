/**
 * CSV / Data export utilities with UTF-8 BOM support for Excel compatibility.
 */

export function exportToCsv<T extends Record<string, unknown>>(
  filename: string,
  rows: T[],
  columns?: { key: keyof T; header: string }[]
): void {
  if (rows.length === 0) return;

  const cols =
    columns ||
    (Object.keys(rows[0]) as (keyof T)[]).map((k) => ({
      key: k,
      header: String(k),
    }));

  const escapeCell = (val: unknown): string => {
    if (val === null || val === undefined) return '""';
    const str = typeof val === "object" ? JSON.stringify(val) : String(val);
    const escaped = str.replace(/"/g, '""');
    return `"${escaped}"`;
  };

  const headerLine = cols.map((c) => escapeCell(c.header)).join(",");
  const dataLines = rows.map((row) =>
    cols.map((c) => escapeCell(row[c.key])).join(",")
  );

  // Prepend UTF-8 BOM (\uFEFF) so Excel respects UTF-8 encoding
  const csvContent = "\uFEFF" + [headerLine, ...dataLines].join("\r\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
