import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { PriceUpdateJob, PriceUpdateLogItem, PriceUpdateLogsResponse, PriceUpdateValidationError } from "../api";

const LOG_STATUSES = ["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"] as const;
type LogFilter = (typeof LOG_STATUSES)[number];

export default function PriceUpdate() {
  const [file, setFile] = useState<File | null>(null);
  const [duplicateMode, setDuplicateMode] = useState<"error" | "last_wins">("error");
  const [creating, setCreating] = useState(false);
  const [job, setJob] = useState<PriceUpdateJob | null>(null);
  const [logs, setLogs] = useState<PriceUpdateLogsResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<LogFilter>("ALL");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const validationErrors: PriceUpdateValidationError[] = job?.validation.errors ?? [];
  const canStart = !!file && !creating;
  const hasJob = !!job?.job_id;

  useEffect(() => {
    if (!job?.job_id) return;
    if (job.status !== "RUNNING" && job.status !== "PENDING") return;
    const timer = window.setInterval(async () => {
      const next = await api.getPriceUpdateJob(job.job_id);
      setJob(next);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (!job?.job_id) return;
    let alive = true;
    api.getPriceUpdateLogs(job.job_id, { status: statusFilter, query: search || undefined, page, per_page: 100 }).then((resp) => {
      if (!alive) return;
      setLogs(resp);
    });
    return () => {
      alive = false;
    };
  }, [job?.job_id, statusFilter, search, page, job?.stats.processed]);

  const progressPct = useMemo(() => {
    if (!job) return 0;
    if (!job.stats.total) return 0;
    return Math.min(100, (job.stats.processed / job.stats.total) * 100);
  }, [job]);

  async function handleStart() {
    if (!file) return;
    setCreating(true);
    setError(null);
    setPage(1);
    try {
      const created = await api.createPriceUpdateJob(file, duplicateMode);
      setJob(created);
      if (created.status === "FAILED" && created.validation.invalid_rows > 0) {
        setError("Walidacja CSV nie przeszła. Popraw błędy i uruchom ponownie.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się uruchomić joba.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Aktualizacja cen</h2>
        <p className="text-sm text-slate-500">CSV po kodach produktów, postęp na żywo i logi operacji.</p>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">1) Upload i walidacja</h3>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm"
          />
          <select
            value={duplicateMode}
            onChange={(e) => setDuplicateMode(e.target.value as "error" | "last_wins")}
            className="rounded-md border border-slate-200 px-2 py-1.5 text-sm"
          >
            <option value="error">Duplikaty: błąd</option>
            <option value="last_wins">Duplikaty: ostatni wygrywa</option>
          </select>
          <button
            type="button"
            onClick={handleStart}
            disabled={!canStart}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {creating ? "Uruchamianie..." : "Uruchom aktualizację"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Wymagane kolumny: <code>code</code>, <code>price</code>. Opcjonalne: <code>currency</code>, <code>price_type</code>, <code>comment</code>.
        </p>
        {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}

        {validationErrors.length > 0 ? (
          <div className="mt-4 overflow-auto max-h-52 border border-rose-100 rounded-md">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-rose-50">
                <tr className="text-left text-rose-700">
                  <th className="px-3 py-2">row_number</th>
                  <th className="px-3 py-2">code</th>
                  <th className="px-3 py-2">error_message</th>
                </tr>
              </thead>
              <tbody>
                {validationErrors.map((e, idx) => (
                  <tr key={`${e.row_number}-${idx}`} className="border-t border-rose-100">
                    <td className="px-3 py-1.5">{e.row_number}</td>
                    <td className="px-3 py-1.5">{e.code || "—"}</td>
                    <td className="px-3 py-1.5">{e.error_message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {hasJob && job ? (
        <>
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">2) Postęp</h3>
            <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Status: <span className="font-semibold">{job.status}</span> · {progressPct.toFixed(1)}%
            </p>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mt-4">
              <Metric label="Total" value={job.stats.total} />
              <Metric label="Processed" value={job.stats.processed} />
              <Metric label="Success" value={job.stats.success} />
              <Metric label="Failed" value={job.stats.failed} />
              <Metric label="Skipped" value={job.stats.skipped} />
              <Metric label="Success rate" value={`${job.stats.success_rate}%`} />
            </div>
          </div>

          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h3 className="text-sm font-semibold text-slate-700">3) Logi</h3>
              <div className="flex items-center gap-2">
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value as LogFilter);
                    setPage(1);
                  }}
                  className="rounded-md border border-slate-200 px-2 py-1.5 text-sm"
                >
                  {LOG_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <input
                  placeholder="Szukaj po code"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                  className="rounded-md border border-slate-200 px-2 py-1.5 text-sm"
                />
                <a
                  href={api.getPriceUpdateLogsExportUrl(job.job_id)}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Pobierz log CSV
                </a>
              </div>
            </div>

            <div className="overflow-auto max-h-[420px]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="text-left text-slate-500 border-b border-slate-200">
                    <th className="py-2">Row</th>
                    <th className="py-2">Code</th>
                    <th className="py-2 text-right">Old</th>
                    <th className="py-2 text-right">New</th>
                    <th className="py-2">Status</th>
                    <th className="py-2">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {(logs?.items ?? []).map((l: PriceUpdateLogItem) => (
                    <tr key={`${l.row_number}-${l.code}-${l.timestamp}`} className="border-t border-slate-100">
                      <td className="py-1.5">{l.row_number}</td>
                      <td className="py-1.5 font-medium">{l.code}</td>
                      <td className="py-1.5 text-right">{l.old_price == null ? "—" : l.old_price.toFixed(2)}</td>
                      <td className="py-1.5 text-right">{l.new_price == null ? "—" : l.new_price.toFixed(2)}</td>
                      <td className="py-1.5">{l.status}</td>
                      <td className="py-1.5">{l.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-between text-sm text-slate-500">
              <span>
                {logs ? `Strona ${logs.page}/${Math.max(logs.pages, 1)} · ${logs.total} wpisów` : "Brak logów"}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={!logs || page <= 1}
                  className="rounded border border-slate-200 px-2 py-1 disabled:opacity-50"
                >
                  Wstecz
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!logs || page >= logs.pages}
                  className="rounded border border-slate-200 px-2 py-1 disabled:opacity-50"
                >
                  Dalej
                </button>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
