/**
 * Virtualized DataTable Component built on TanStack Table and TanStack Virtual.
 * Designed for NOC high-density telemetry and device inventories (10,000+ rows).
 */
import { useRef, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  SortingState,
  ColumnDef,
  flexRender,
  RowSelectionState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Download,
  SlidersHorizontal,
} from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import { exportToCsv } from "@/utils/export";
import { usePrefsStore } from "@/store/prefs";
import { cn } from "@/utils/cn";

export interface DataTableProps<TData> {
  data: TData[];
  columns: ColumnDef<TData, unknown>[];
  title?: string;
  filterPlaceholder?: string;
  exportFilename?: string;
  enableSelection?: boolean;
  onRowClick?: (row: TData) => void;
  isLoading?: boolean;
  emptyMessage?: string;
  height?: number | string;
  className?: string;
}

export function DataTable<TData extends object>({
  data,
  columns,
  title,
  filterPlaceholder = "Filter rows...",
  exportFilename = "export_data",
  enableSelection = false,
  onRowClick,
  isLoading = false,
  emptyMessage = "No matching records found.",
  height,
  className,
}: DataTableProps<TData>) {
  const { density } = usePrefsStore();
  const rowHeight = density === "compact" ? 28 : 36;

  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // Table instance
  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      globalFilter,
      rowSelection,
    },
    enableRowSelection: enableSelection,
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const { rows } = table.getRowModel();

  // Virtualizer for high-fps scrolling over 10,000 rows
  const tableContainerRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => rowHeight,
    overscan: 15,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();

  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? totalSize - virtualRows[virtualRows.length - 1].end
      : 0;

  const handleExportCsv = () => {
    const visibleData = rows.map((r) => r.original);
    const visibleCols = table
      .getVisibleLeafColumns()
      .filter((c) => c.id !== "select")
      .map((c) => ({
        key: c.id,
        header: typeof c.columnDef.header === "string" ? c.columnDef.header : c.id,
      }));
    exportToCsv(exportFilename, visibleData as Record<string, unknown>[], visibleCols);
  };

  return (
    <div
      style={height ? { height } : undefined}
      className={cn("flex flex-1 flex-col overflow-hidden border border-line rounded-control bg-surface", className)}
    >
      {/* Table Toolbar */}
      <div className="flex h-10 flex-shrink-0 items-center justify-between border-b border-line px-3 gap-2 bg-surface">
        <div className="flex items-center gap-3 max-w-sm w-full">
          {title && (
            <span className="font-semibold text-xs text-ink uppercase tracking-wider whitespace-nowrap">
              {title}
            </span>
          )}
          {/* Global Search */}
          <div className="flex items-center gap-2 flex-1">
            <Search className="h-3.5 w-3.5 text-ink-2 flex-shrink-0" />
            <input
              type="text"
              value={globalFilter ?? ""}
              onChange={(e) => setGlobalFilter(e.target.value)}
              placeholder={filterPlaceholder}
              className="h-7 w-full rounded-control border border-line bg-surface-2 px-2 text-xs text-ink placeholder-ink-2/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
            />
          </div>
        </div>

        {/* Right Tools: Row Count, Column Visibility, CSV Export */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-ink-2">
            {table.getFilteredRowModel().rows.length.toLocaleString()}{" "}
            {table.getFilteredRowModel().rows.length === 1 ? "row" : "rows"}
            {Object.keys(rowSelection).length > 0 && (
              <span className="text-signal ml-1">
                ({Object.keys(rowSelection).length} selected)
              </span>
            )}
          </span>

          {/* Column Visibility Popover */}
          <Popover.Root>
            <Popover.Trigger asChild>
              <button
                type="button"
                aria-label="Toggle columns"
                className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
              >
                <SlidersHorizontal className="h-3 w-3" />
                <span className="hidden sm:inline">Columns</span>
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content className="z-50 w-48 rounded-control border border-line bg-surface p-2 shadow-floating text-xs">
                <div className="font-semibold text-ink px-1 pb-1 mb-1 border-b border-line">
                  Toggle Columns
                </div>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {table.getAllLeafColumns().map((column) => {
                    if (column.id === "select") return null;
                    return (
                      <label
                        key={column.id}
                        className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-ink hover:bg-surface-2"
                      >
                        <input
                          type="checkbox"
                          checked={column.getIsVisible()}
                          onChange={column.getToggleVisibilityHandler()}
                          className="rounded border-line text-signal focus:ring-signal"
                        />
                        <span className="truncate">
                          {typeof column.columnDef.header === "string"
                            ? column.columnDef.header
                            : column.id}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>

          {/* CSV Export Button */}
          <button
            type="button"
            onClick={handleExportCsv}
            title="Export filtered view as CSV"
            className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface px-2 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
          >
            <Download className="h-3 w-3" />
            <span className="hidden sm:inline">Export</span>
          </button>
        </div>
      </div>

      {/* Virtualized Table Scroll Container */}
      <div
        ref={tableContainerRef}
        className="flex-1 overflow-auto bg-surface"
        style={{ willChange: "transform" }}
      >
        <table className="w-full border-collapse text-xs text-left" style={{ tableLayout: "fixed" }}>
          {/* Sticky Header */}
          <thead className="sticky top-0 z-10 border-b border-line bg-surface-2">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const sortDir = header.column.getIsSorted();

                  return (
                    <th
                      key={header.id}
                      style={{ width: header.getSize() }}
                      className={cn(
                        "px-3 py-1.5 font-semibold text-ink-2 select-none border-r border-line/40 last:border-r-0",
                        canSort && "cursor-pointer hover:bg-surface/60 hover:text-ink"
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="truncate">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                        </span>
                        {canSort && (
                          <span className="text-ink-2/60">
                            {sortDir === "asc" ? (
                              <ArrowUp className="h-3 w-3 text-signal" />
                            ) : sortDir === "desc" ? (
                              <ArrowDown className="h-3 w-3 text-signal" />
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40 hover:opacity-100" />
                            )}
                          </span>
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>

          {/* Virtual Body */}
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-12 text-center text-xs text-ink-2"
                >
                  <div className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-signal border-t-transparent" />
                    <span>Loading rows...</span>
                  </div>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-12 text-center text-xs text-ink-2"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              <>
                {paddingTop > 0 && (
                  <tr>
                    <td style={{ height: `${paddingTop}px` }} />
                  </tr>
                )}
                {virtualRows.map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  const isSelected = row.getIsSelected();

                  return (
                    <tr
                      key={row.id}
                      onClick={() => onRowClick?.(row.original)}
                      className={cn(
                        "border-b border-line/40 transition-colors",
                        virtualRow.index % 2 === 0 ? "bg-surface" : "bg-surface-2/30",
                        isSelected && "bg-signal/10",
                        onRowClick && "cursor-pointer hover:bg-surface-2"
                      )}
                      style={{ height: `${rowHeight}px` }}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          className="px-3 py-0.5 truncate border-r border-line/20 last:border-r-0 text-ink leading-tight"
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext()
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {paddingBottom > 0 && (
                  <tr>
                    <td style={{ height: `${paddingBottom}px` }} />
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
