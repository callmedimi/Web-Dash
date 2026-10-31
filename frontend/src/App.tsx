import React from "react";

export const App: React.FC = () => {
  return (
    <div className="flex h-full w-full flex-col bg-bg text-ink">
      <header className="flex h-12 items-center justify-between border-b border-line bg-surface px-4">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-signal">Web-Dash</span>
          <span className="text-xs text-ink-2">NOC Console</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-xs text-ok">
            <span className="h-2 w-2 rounded-full bg-ok" />
            System Ready
          </span>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-dialog border border-line bg-surface p-6 shadow-floating">
          <h1 className="text-lg font-medium text-ink">Huawei VRP Network Operations Console</h1>
          <p className="mt-2 text-sm text-ink-2">
            Air-gapped enterprise automation platform initialized successfully.
          </p>
        </div>
      </main>
    </div>
  );
};

export default App;
