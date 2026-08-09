import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  PriceUpdateJob,
  PriceUpdateLogItem,
  PriceUpdateLogsResponse,
  PriceUpdateCsvDelimiter,
  PriceUpdateTargetMode,
  PriceUpdateValidationError,
} from "../api";

const CSV_DELIMITERS: { value: PriceUpdateCsvDelimiter; label: string }[] = [
  { value: "semicolon", label: "Średnik (;) — Excel PL" },
  { value: "comma", label: "Przecinek (,)" },
  { value: "tab", label: "Tabulator" },
  { value: "pipe", label: "Pionowa kreska (|)" },
];

const LOG_STATUSES = ["ALL", "SUCCESS", "ERROR", "WARNING", "SKIPPED"] as const;
type LogFilter = (typeof LOG_STATUSES)[number];

const STORAGE_KEY = "price_update_last_job_id";
const SESSION_CACHE_KEY = "price_update_job_cache";

function loadCachedJob(): PriceUpdateJob | null {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PriceUpdateJob;
  } catch {
    return null;
  }
}

function persistJob(job: PriceUpdateJob | null) {
  if (!job?.job_id) return;
  localStorage.setItem(STORAGE_KEY, job.job_id);
  try {
    sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(job));
  } catch {
    /* quota */
  }
}

function clearPersistedJob() {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(SESSION_CACHE_KEY);
}

export default function PriceUpdate() {
  const [file, setFile] = useState<File | null>(null);
  const [targetMode, setTargetMode] = useState<PriceUpdateTargetMode>("product");
  const [duplicateMode, setDuplicateMode] = useState<"error" | "last_wins">("error");
  const [csvDelimiter, setCsvDelimiter] = useState<PriceUpdateCsvDelimiter>("semicolon");
  const [keepExtraVariants, setKeepExtraVariants] = useState(false);
  const [creating, setCreating] = useState(false);
  const [job, setJobState] = useState<PriceUpdateJob | null>(() => loadCachedJob());
  const [logs, setLogs] = useState<PriceUpdateLogsResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<LogFilter>("ALL");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [reconnectError, setReconnectError] = useState<string | null>(null);
  const jobRef = useRef<PriceUpdateJob | null>(null);

  const setJob = useCallback((next: PriceUpdateJob | null) => {
    jobRef.current = next;
    setJobState(next);
    if (next) persistJob(next);
  }, []);

  const fetchJobById = useCallback(async (jobId: string): Promise<PriceUpdateJob | null> => {
    try {
      return await api.getPriceUpdateJob(jobId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.startsWith("404")) {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === jobId) localStorage.removeItem(STORAGE_KEY);
      }
      return null;
    }
  }, []);

  const reconnectJob = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRestoring(true);
    setReconnectError(null);
    try {
      // 1) Aktywny job na serwerze ma pierwszeństwo (RUNNING trwa mimo utraty localStorage)
      const { job: active } = await api.getActivePriceUpdateJob();
      if (active?.job_id) {
        const full = await fetchJobById(active.job_id);
        if (full) {
          setJob(full);
          return;
        }
        setJob(active as PriceUpdateJob);
        return;
      }

      // 2) Ostatni zapisany job_id
      const savedId = localStorage.getItem(STORAGE_KEY);
      if (savedId) {
        const j = await fetchJobById(savedId);
        if (j) {
          setJob(j);
          return;
        }
      }

      // 3) Ostatni job na serwerze (DB) — po restarcie backendu
      const { job: latest } = await api.getLatestPriceUpdateJob();
      if (latest?.job_id) {
        const full = await fetchJobById(latest.job_id);
        if (full) {
          setJob(full);
          return;
        }
        setJob(latest as PriceUpdateJob);
        return;
      }

      // 4) Cache sesji — tylko jeśli job nadal istnieje na serwerze
      const cached = loadCachedJob();
      if (cached?.job_id) {
        const j = await fetchJobById(cached.job_id);
        if (j) {
          setJob(j);
          return;
        }
        // Stary cache (np. RUNNING) po restarcie backendu — wyczyść
        clearPersistedJob();
        setJobState(null);
        jobRef.current = null;
      }
    } catch (e) {
      setReconnectError(e instanceof Error ? e.message : "Nie udało się połączyć z jobem");
    } finally {
      if (showSpinner) setRestoring(false);
    }
  }, [fetchJobById, setJob]);

  // Przywróć / podłącz job (mount, powrót na zakładkę, focus okna)
  useEffect(() => {
    void reconnectJob(true);
    const onVisible = () => {
      if (document.visibilityState === "visible") void reconnectJob(false);
    };
    const onFocus = () => void reconnectJob(false);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onFocus);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onFocus);
    };
  }, [reconnectJob]);

  // Krótki retry po wejściu (np. job właśnie startuje) — bez nieskończonego pollingu
  useEffect(() => {
    if (job?.job_id) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (attempts > 5) {
        window.clearInterval(timer);
        return;
      }
      void reconnectJob(false);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, reconnectJob]);

  const validationErrors: PriceUpdateValidationError[] = job?.validation.errors ?? [];
  const isXlsx = file?.name?.toLowerCase().endsWith(".xlsx") ?? false;
  const isSql = file?.name?.toLowerCase().endsWith(".sql") ?? false;
  const canStart = !!file && !creating;
  const hasJob = !!job?.job_id;
  const isVariantMode = targetMode === "variant";

  const fetchLogsParams = useMemo(
    () => ({
      status: statusFilter,
      query: search || undefined,
      page,
      per_page: 100,
    }),
    [statusFilter, search, page],
  );

  const isJobTerminal =
    job?.status === "DONE" || job?.status === "FAILED" || job?.status === "CANCELLED";
  const jobId = job?.job_id;
  const jobRunning = job?.status === "RUNNING" || job?.status === "PENDING";

  // Postęp — tylko lekki endpoint job (bez logów)
  useEffect(() => {
    if (!jobId || isJobTerminal) return;
    let alive = true;

    async function refreshJob() {
      try {
        const nextJob = await api.getPriceUpdateJob(jobId);
        if (alive) setJob(nextJob);
      } catch {
        /* retry */
      }
    }

    void refreshJob();
    const timer = window.setInterval(refreshJob, 2000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [jobId, isJobTerminal]);

  // Logi — osobno; podczas RUNNING tylko ostatnie wpisy (tail)
  useEffect(() => {
    if (!jobId) return;
    let alive = true;

    async function refreshLogs() {
      try {
        const params = jobRunning
          ? { ...fetchLogsParams, tail: 200, page: 1 }
          : fetchLogsParams;
        const nextLogs = await api.getPriceUpdateLogs(jobId, params);
        if (alive) setLogs(nextLogs);
      } catch {
        /* retry */
      }
    }

    void refreshLogs();
    if (isJobTerminal) return () => {
      alive = false;
    };

    const intervalMs = jobRunning ? 3000 : 5000;
    const timer = window.setInterval(refreshLogs, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [jobId, isJobTerminal, jobRunning, fetchLogsParams]);

  useEffect(() => {
    if (!jobId || !isJobTerminal) return;
    api.getPriceUpdateJob(jobId).then(setJob).catch(() => undefined);
  }, [jobId, isJobTerminal]);

  const progressPct = useMemo(() => {
    if (!job) return 0;
    if (job.status === "DONE" || job.status === "FAILED" || job.status === "CANCELLED") return 100;
    if (!job.stats.total) return 0;
    if (job.stats.processed >= job.stats.total && job.status === "RUNNING") {
      return 95;
    }
    return Math.min(95, (job.stats.processed / job.stats.total) * 100);
  }, [job]);

  async function handleStart() {
    if (!file) return;
    setCreating(true);
    setError(null);
    setPage(1);
    setLogs(null);
    try {
      const created = await api.createPriceUpdateJob(file, {
        duplicate_mode: duplicateMode,
        target_mode: targetMode,
        csv_delimiter: csvDelimiter,
        disable_extra_variants: !keepExtraVariants,
      });
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

  async function handleCancel() {
    if (!job?.job_id) return;
    setCancelling(true);
    try {
      await api.cancelPriceUpdateJob(job.job_id);
    } catch {
      /* ignoruj — polling i tak zaktualizuje status */
    } finally {
      setCancelling(false);
    }
  }

  function handleNewJob() {
    setJobState(null);
    jobRef.current = null;
    setLogs(null);
    setFile(null);
    setError(null);
    setReconnectError(null);
    setPage(1);
    clearPersistedJob();
  }

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-2xl font-bold">Aktualizacja cen</h2>
          <div className="flex gap-2">
            {hasJob && jobRunning && (
              <button
                type="button"
                onClick={handleCancel}
                disabled={cancelling}
                className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {cancelling ? "Zatrzymywanie…" : "Zatrzymaj"}
              </button>
            )}
            {hasJob && isJobTerminal && (
              <button
                type="button"
                onClick={handleNewJob}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Nowy job
              </button>
            )}
          </div>
        </div>
        <p className="text-sm text-slate-500">
          Plik CSV lub TXT po kodach {isVariantMode ? "wariantów" : "produktów"}, postęp na żywo i logi operacji.
        </p>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <div className="flex flex-col items-center py-4 mb-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400 mb-4">Tryb aktualizacji</p>
          <div className="inline-flex w-full max-w-md rounded-xl border border-slate-200 p-1 bg-slate-50">
            <ModeSwitch
              active={targetMode === "product"}
              label="Produkty"
              onClick={() => setTargetMode("product")}
            />
            <ModeSwitch
              active={targetMode === "variant"}
              label="Warianty"
              onClick={() => setTargetMode("variant")}
            />
          </div>
        </div>

        <h3 className="text-sm font-semibold text-slate-700 mb-3 mt-2">1) Upload i walidacja</h3>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv,.txt,.text,.xlsx,.sql,text/csv,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm"
          />
          {!isXlsx && (
            <select
              value={csvDelimiter}
              onChange={(e) => setCsvDelimiter(e.target.value as PriceUpdateCsvDelimiter)}
              className="rounded-md border border-slate-200 px-2 py-1.5 text-sm"
              title="Separator kolumn w pliku CSV"
            >
              {CSV_DELIMITERS.map((d) => (
                <option key={d.value} value={d.value}>
                  Separator: {d.label}
                </option>
              ))}
            </select>
          )}
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

        {isXlsx && (
          <p className="mt-2 text-xs text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-3 py-1.5">
            Plik XLSX — przetwarzane są arkusze z kolumnami <code>code</code> i <code>price</code>. Puste wiersze są pomijane.
          </p>
        )}
        {isSql && (
          <p className="mt-2 text-xs text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-3 py-1.5">
            Plik SQL — wyciągam kody i ceny z instrukcji <code>INSERT INTO ... VALUES</code>.
            Pliki <code>.csv</code>/<code>.txt</code> z treścią SQL są też rozpoznawane automatycznie.
          </p>
        )}

        {isVariantMode && (
          <label className="mt-3 flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={keepExtraVariants}
              onChange={(e) => setKeepExtraVariants(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-slate-700">
              Nie wyłączaj istniejących wariantów, których nie ma w pliku
            </span>
          </label>
        )}

        <p className="mt-2 text-xs text-slate-500">
          {isXlsx
            ? <>Plik <code>.xlsx</code> — przetwarzane są tylko arkusze z nagłówkiem zawierającym kolumny <code>code</code> i <code>price</code>. Pozostałe arkusze są pomijane.</>
            : isSql
            ? <>Plik <code>.sql</code> — wyciągam wiersze z <code>INSERT INTO ... VALUES(code, code, price, ...)</code>. Pliki <code>.csv</code>/<code>.txt</code> z treścią SQL są też wykrywane automatycznie.</>
            : <>Plik <code>.csv</code> lub <code>.txt</code> z nagłówkiem. Wymagane kolumny: <code>code</code>, <code>price</code>. Opcjonalne: <code>currency</code>, <code>price_type</code>, <code>comment</code>.</>
          }
          {isVariantMode ? (
            <>
              {" "}
              W trybie wariantów <code>code</code> to kod wariantu.{" "}
              {keepExtraVariants
                ? "Warianty spoza pliku pozostaną bez zmian."
                : "Po aktualizacji cen wyłączone zostaną warianty rozszerzone (extended) spoza pliku — tylko u produktów z co najmniej jednym wierszem w CSV."}
            </>
          ) : null}
        </p>

        {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}

        {restoring && !hasJob ? (
          <p className="mt-3 text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
            Szukam aktywnego joba na serwerze…
          </p>
        ) : null}

        {reconnectError && !hasJob ? (
          <p className="mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
            {reconnectError}
          </p>
        ) : null}

        {hasJob && (job?.status === "RUNNING" || job?.status === "PENDING") && reconnectError ? (
          <p className="mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
            {reconnectError} (pokazuję ostatni znany stan — odświeżam w tle)
          </p>
        ) : null}

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
            {isJobTerminal ? (
              <p className="text-xs text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-md px-3 py-2 mb-3">
                Job zapisany na serwerze
                {job.finished_at ? ` · zakończony ${job.finished_at.slice(0, 19).replace("T", " ")}` : ""}.
                Logi i postęp są dostępne po restarcie — możesz pobrać pełny CSV poniżej.
              </p>
            ) : null}
            <p className="text-xs text-slate-500 mb-2">
              Tryb: {job.target_mode === "variant" ? "warianty" : "produkty"}
              {job.csv_delimiter
                ? ` · separator: ${CSV_DELIMITERS.find((d) => d.value === job.csv_delimiter)?.label ?? job.csv_delimiter}`
                : ""}
              {job.target_mode === "variant"
                ? job.disable_extra_variants === false
                  ? " · warianty spoza pliku: zachowane"
                  : " · warianty spoza pliku: wyłączane"
                : ""}
            </p>
            <div className="w-full h-3 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Status: <span className="font-semibold">{job.status}</span> · {progressPct.toFixed(1)}%
              {job.stats.logs_total != null ? ` · ${job.stats.logs_total} wpisów w logu` : ""}
              {job.status === "RUNNING" && job.stats.eta_seconds != null
                ? ` · ETA: ${fmtEta(job.stats.eta_seconds)}`
                : ""}
              {job.status === "RUNNING" && job.stats.processed >= job.stats.total
                ? " · finalizacja produktów…"
                : ""}
            </p>
            {jobRunning && job.stats.current_code ? (
              <p className="mt-1 text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 rounded px-2 py-1">
                Teraz: {fmtPhase(job.stats.current_phase)}
                {job.stats.current_row_number
                  ? ` · wiersz ${job.stats.current_row_number}/${job.stats.total}`
                  : ""}
                {" · "}
                <span className="font-mono">{job.stats.current_code}</span>
              </p>
            ) : null}
            {job.fatal_error ? (
              <p className="mt-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
                {job.fatal_error}
              </p>
            ) : null}
            <div className="grid grid-cols-2 md:grid-cols-8 gap-3 mt-2">
              <Metric label="Wierszy" value={job.stats.total} />
              <Metric label="Przetworzono" value={job.stats.processed} />
              <Metric label="Cena OK" value={job.stats.success} />
              <Metric label="Błąd wiersza" value={job.stats.failed} />
              <Metric label="Bez zmian" value={job.stats.skipped} />
              <Metric label="Ostrzeżenia" value={job.stats.warning} />
              {job.target_mode === "variant" ? (
                <Metric label="Wył. warianty" value={job.stats.deactivated_variants ?? 0} />
              ) : null}
              <Metric label="Skuteczność" value={`${job.stats.success_rate}%`} />
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
                      <td className="py-1.5">{l.row_number || "—"}</td>
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
                {logs
                  ? `Strona ${logs.page}/${Math.max(logs.pages, 1)} · ${logs.total} wpisów łącznie`
                  : "Brak logów"}
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

function fmtEta(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}min`;
}

function fmtPhase(phase: string | null | undefined): string {
  switch (phase) {
    case "row":
      return "aktualizacja wiersza";
    case "post_process":
      return "finalizacja produktu";
    default:
      return phase ?? "…";
  }
}

function ModeSwitch({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-6 py-3 text-base font-semibold rounded-lg transition-colors ${
        active ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
      }`}
    >
      {label}
    </button>
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
