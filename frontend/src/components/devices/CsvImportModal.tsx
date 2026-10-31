import React, { useState } from "react";
import { Upload, X, CheckCircle2, AlertTriangle, FileText } from "lucide-react";
import { apiClient } from "@/api/client";
import { CsvImportSummary } from "@/api/types";

export interface CsvImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const CsvImportModal: React.FC<CsvImportModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [file, setFile] = useState<File | null>(null);
  const [updateExisting, setUpdateExisting] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<CsvImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a CSV file to import.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("update_existing", String(updateExisting));

      const res = await apiClient.post<CsvImportSummary>("/api/v1/devices/import-csv", formData);
      setResult(res);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to import CSV file");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-dialog border border-line bg-surface p-5 shadow-floating">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-signal" />
            <h3 className="text-sm font-semibold text-ink">Import Huawei NMS CSV</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control p-1 text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="space-y-4 py-4 text-xs">
          <p className="text-ink-2">
            Upload a Huawei U2000 / iMaster NCE export CSV file. Expected columns include:{" "}
            <span className="font-mono text-[11px] text-ink">NE Name</span>,{" "}
            <span className="font-mono text-[11px] text-ink">NE IP Address</span>,{" "}
            <span className="font-mono text-[11px] text-ink">NE Type</span>, etc.
          </p>

          {/* File Input Box */}
          <div className="flex flex-col items-center justify-center rounded-control border-2 border-dashed border-line bg-surface-2/40 p-6 text-center hover:border-signal/50 transition-colors">
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={handleFileChange}
              id="csv-file-upload"
              className="sr-only"
            />
            <label
              htmlFor="csv-file-upload"
              className="cursor-pointer flex flex-col items-center space-y-2"
            >
              <FileText className="h-8 w-8 text-signal" />
              {file ? (
                <div className="font-mono text-xs font-semibold text-ink">{file.name}</div>
              ) : (
                <>
                  <span className="font-semibold text-signal hover:underline">Choose CSV file</span>
                  <span className="text-[11px] text-ink-2">or drag and drop file here</span>
                </>
              )}
            </label>
          </div>

          {/* Options */}
          <label className="flex items-center gap-2 cursor-pointer text-ink">
            <input
              type="checkbox"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
              className="rounded border-line text-signal focus:ring-signal"
            />
            <span>Update existing devices if matching name or IP found</span>
          </label>

          {/* Error Banner */}
          {error && (
            <div className="flex items-center gap-2 rounded-control border border-fault/30 bg-fault/10 p-3 text-xs text-fault">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Success Summary */}
          {result && (
            <div className="rounded-control border border-ok/30 bg-ok/10 p-3 space-y-1.5 text-xs text-ok">
              <div className="font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4" />
                <span>Import Completed Successfully</span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-center pt-2">
                <div className="rounded bg-surface p-1.5 border border-line">
                  <div className="text-[10px] text-ink-2">Total</div>
                  <div className="font-mono font-bold text-ink">{result.total_rows ?? 0}</div>
                </div>
                <div className="rounded bg-surface p-1.5 border border-line">
                  <div className="text-[10px] text-ok">New</div>
                  <div className="font-mono font-bold text-ok">{result.imported ?? 0}</div>
                </div>
                <div className="rounded bg-surface p-1.5 border border-line">
                  <div className="text-[10px] text-signal">Updated</div>
                  <div className="font-mono font-bold text-signal">{result.updated ?? 0}</div>
                </div>
                <div className="rounded bg-surface p-1.5 border border-line">
                  <div className="text-[10px] text-warn">Skipped</div>
                  <div className="font-mono font-bold text-warn">{result.skipped ?? 0}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-line pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-control border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink transition-colors"
          >
            {result ? "Close" : "Cancel"}
          </button>
          {!result && (
            <button
              type="button"
              onClick={handleUpload}
              disabled={!file || isUploading}
              className="inline-flex items-center gap-1.5 rounded-control bg-signal px-3.5 py-1.5 text-xs font-medium text-white hover:bg-signal/90 disabled:opacity-50 transition-colors shadow-sm"
            >
              <Upload className="h-3 w-3" />
              <span>{isUploading ? "Importing..." : "Start Import"}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
