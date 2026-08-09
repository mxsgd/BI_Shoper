import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  ApplyCodesJob,
  DetectedOptionGroup,
  OptionGroupConfig,
  VariantGroup,
  VariantProduct,
} from "../api";

// ─── types ────────────────────────────────────────────────────────────────────

interface MappedGroup {
  group_id: string;
  role: string;
  values: { value_id: string; value_name: string; suffix: string }[];
  /** Full pool of values defined in Shoper for this group — for manual "add from pool". */
  available: { value_id: string; value_name: string; suggested_suffix: string }[];
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function groupSubtitle(grp: { group_id: number; product_count: number }) {
  return `id: ${grp.group_id} · ${grp.product_count} prod.`;
}

/** Shows a small popup with full text when truncated label is hovered. */
function TruncateTooltip({ text, className = "" }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setTruncated(el.scrollWidth > el.clientWidth + 1);
    check();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(check) : null;
    ro?.observe(el);
    window.addEventListener("resize", check);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", check);
    };
  }, [text]);

  return (
    <span
      className="relative block w-full min-w-0"
      onMouseEnter={() => truncated && setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span ref={ref} className={`block truncate ${className}`}>
        {text}
      </span>
      {open && truncated && (
        <span
          role="tooltip"
          className="absolute z-50 left-0 top-full mt-1 px-2 py-1 text-[11px] leading-snug text-slate-700 bg-white border border-slate-200 rounded-md shadow-md max-w-[16rem] whitespace-normal pointer-events-none"
        >
          {text}
        </span>
      )}
    </span>
  );
}

function downloadCsv(rows: string[][], filename: string) {
  const text = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + text], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function parsePricesCsv(text: string): Record<string, number> {
  const prices: Record<string, number> = {};
  const lines = text.split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    const sep = line.includes(";") ? ";" : ",";
    const parts = line.split(sep).map((c) => c.trim().replace(/^"|"$/g, ""));
    if (parts.length >= 2) {
      const code = parts[0].toUpperCase();
      const price = parseFloat(parts[1].replace(",", "."));
      if (code && !isNaN(price)) prices[code] = price;
    }
  }
  return prices;
}

function parseMappingCsv(text: string): MappedGroup[] {
  const lines = text.split(/\r?\n/).filter(Boolean);
  const groups: Map<string, MappedGroup> = new Map();
  for (const line of lines.slice(1)) {
    const sep = line.includes(";") ? ";" : ",";
    const parts = line.split(sep).map((c) => c.trim().replace(/^"|"$/g, ""));
    if (parts.length < 4) continue;
    const [group_id, role, value_id, value_name, suffix = ""] = parts;
    if (!groups.has(group_id)) {
      groups.set(group_id, { group_id, role, values: [], available: [] });
    }
    groups.get(group_id)!.values.push({ value_id, value_name, suffix });
  }
  return Array.from(groups.values());
}

function buildMappingCsvRows(groups: MappedGroup[]): string[][] {
  const rows: string[][] = [["group_id", "role", "value_id", "value_name", "suffix"]];
  for (const g of groups) {
    for (const v of g.values) {
      rows.push([g.group_id, g.role, v.value_id, v.value_name, v.suffix]);
    }
  }
  return rows;
}

function cartesian<T>(arrays: T[][]): T[][] {
  if (!arrays.length) return [[]];
  return arrays.reduce<T[][]>(
    (acc, arr) => acc.flatMap((a) => arr.map((v) => [...a, v])),
    [[]],
  );
}

// ─── step badge ───────────────────────────────────────────────────────────────

function StepBadge({ n, active, done }: { n: number; active: boolean; done: boolean }) {
  return (
    <div
      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
        done
          ? "bg-emerald-500 text-white"
          : active
          ? "bg-indigo-600 text-white"
          : "bg-slate-200 text-slate-500"
      }`}
    >
      {done ? (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        n
      )}
    </div>
  );
}

// ─── role badge ───────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    size: { label: "Rozmiar", cls: "bg-sky-100 text-sky-700" },
    fabric: { label: "Tkanina", cls: "bg-amber-100 text-amber-700" },
    other: { label: "Inne", cls: "bg-slate-100 text-slate-600" },
  };
  const { label, cls } = map[role] ?? map.other;
  return <span className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>{label}</span>;
}

// ─── progress bar ─────────────────────────────────────────────────────────────

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="relative h-2 bg-slate-100 rounded-full overflow-hidden">
      <div
        className="absolute inset-y-0 left-0 bg-indigo-500 transition-all duration-300 rounded-full"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

export default function VariantCodes() {
  // ── Step 1: group picker ──────────────────────────────────────────────────
  const [groups, setGroups] = useState<VariantGroup[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [groupSearch, setGroupSearch] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<VariantGroup | null>(null);
  const [groupSyncing, setGroupSyncing] = useState(false);
  const [groupSyncError, setGroupSyncError] = useState<string | null>(null);

  // ── Step 2: product picker ────────────────────────────────────────────────
  const [allProducts, setAllProducts] = useState<VariantProduct[]>([]);
  const [prodsLoading, setProdsLoading] = useState(false);
  const [productSearch, setProductSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // ── Step 3: option mapping ────────────────────────────────────────────────
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);
  const [mappedGroups, setMappedGroups] = useState<MappedGroup[]>([]);

  // prices from CSV
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [pricesFilename, setPricesFilename] = useState<string | null>(null);
  const priceFileRef = useRef<HTMLInputElement>(null);
  const mappingFileRef = useRef<HTMLInputElement>(null);

  // ── Step 4: apply job ─────────────────────────────────────────────────────
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<ApplyCodesJob | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  // ── Step 4: supplement (dogeneruj) job ────────────────────────────────────
  const [suppJobId, setSuppJobId] = useState<string | null>(null);
  const [suppJob, setSuppJob] = useState<ApplyCodesJob | null>(null);
  const [suppStartError, setSuppStartError] = useState<string | null>(null);
  const suppPollRef = useRef<number | null>(null);

  // ── Load groups on mount (sync names from /option-groups — fast) ───────
  useEffect(() => {
    api.getVariantGroups({ refresh: true })
      .then(setGroups)
      .catch(() => setGroups([]))
      .finally(() => setGroupsLoading(false));
  }, []);

  const selectGroup = useCallback(async (grp: VariantGroup) => {
    setGroupSyncError(null);
    setSelectedGroup(grp);
    setAllProducts([]);
    setSelectedIds(new Set());
    setProductSearch("");
    setMappedGroups([]);
    setPendingPoolValue({});
    setDetectError(null);
    setJobId(null);
    setJob(null);

    // 1. Show products from local DB immediately
    setProdsLoading(true);
    try {
      const cached = await api.searchVariantProducts({ group_id: grp.group_id, limit: 500 });
      setAllProducts(cached);
    } catch {
      setAllProducts([]);
    } finally {
      setProdsLoading(false);
    }

    // 2. Refresh group + products from Shoper in background (no stocks — too slow)
    setGroupSyncing(true);
    try {
      const res = await api.syncVariantGroup(grp.group_id);
      setSelectedGroup(res.group);
      setGroups((prev) => prev.map((g) => (g.group_id === res.group.group_id ? res.group : g)));
      const fresh = await api.searchVariantProducts({ group_id: res.group.group_id, limit: 500 });
      setAllProducts(fresh);
    } catch (e) {
      setGroupSyncError(e instanceof Error ? e.message : "Błąd synchronizacji zestawu");
    } finally {
      setGroupSyncing(false);
    }
  }, []);

  const filteredGroups = useMemo(() => {
    const q = groupSearch.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter(
      (g) =>
        g.name.toLowerCase().includes(q) ||
        String(g.group_id).includes(q),
    );
  }, [groups, groupSearch]);

  const filteredProducts = useMemo(() => {
    const q = productSearch.trim().toLowerCase();
    return q
      ? allProducts.filter((p) => p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q))
      : allProducts;
  }, [allProducts, productSearch]);

  const toggleProduct = (p: VariantProduct) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(p.product_id)) next.delete(p.product_id);
      else next.add(p.product_id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === filteredProducts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredProducts.map((p) => p.product_id)));
    }
  };

  // ── Detect options (Step 3) ───────────────────────────────────────────────
  const detectOptions = useCallback(async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setDetecting(true);
    setDetectError(null);
    try {
      // Multi-product detect → returns intersection of option groups
      const res = ids.length === 1
        ? await api.detectOptions(ids[0])
        : await api.detectOptionsMulti(ids);
      const mapped: MappedGroup[] = res.groups.map((g: DetectedOptionGroup) => ({
        group_id: g.group_id,
        role: g.role,
        values: g.values.map((v) => ({
          value_id: v.value_id,
          value_name: v.value_name,
          suffix: v.suggested_suffix,
        })),
        available: (g.available_values ?? []).map((v) => ({
          value_id: v.value_id,
          value_name: v.value_name,
          suggested_suffix: v.suggested_suffix,
        })),
      }));
      setMappedGroups(mapped);
    } catch (e) {
      setDetectError(e instanceof Error ? e.message : "Błąd wykrywania opcji");
    } finally {
      setDetecting(false);
    }
  }, [selectedIds]);

  const updateSuffix = (gIdx: number, vIdx: number, val: string) => {
    setMappedGroups((prev) =>
      prev.map((g, gi) =>
        gi !== gIdx
          ? g
          : {
              ...g,
              values: g.values.map((v, vi) => (vi !== vIdx ? v : { ...v, suffix: val })),
            },
      ),
    );
  };

  const updateRole = (gIdx: number, role: string) => {
    setMappedGroups((prev) => prev.map((g, gi) => (gi !== gIdx ? g : { ...g, role })));
  };

  const moveGroup = (gIdx: number, dir: -1 | 1) => {
    setMappedGroups((prev) => {
      const next = [...prev];
      const target = gIdx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[gIdx], next[target]] = [next[target], next[gIdx]];
      return next;
    });
  };

  /** Selected "add from pool" value_id per group index (controlled <select>). */
  const [pendingPoolValue, setPendingPoolValue] = useState<Record<number, string>>({});

  const addValueFromPool = (gIdx: number) => {
    const valueId = pendingPoolValue[gIdx];
    if (!valueId) return;
    setMappedGroups((prev) =>
      prev.map((g, gi) => {
        if (gi !== gIdx) return g;
        if (g.values.some((v) => v.value_id === valueId)) return g;
        const pooled = g.available.find((v) => v.value_id === valueId);
        if (!pooled) return g;
        return {
          ...g,
          values: [
            ...g.values,
            { value_id: pooled.value_id, value_name: pooled.value_name, suffix: pooled.suggested_suffix },
          ],
        };
      }),
    );
    setPendingPoolValue((prev) => ({ ...prev, [gIdx]: "" }));
  };

  const removeValue = (gIdx: number, vIdx: number) => {
    setMappedGroups((prev) =>
      prev.map((g, gi) =>
        gi !== gIdx ? g : { ...g, values: g.values.filter((_, vi) => vi !== vIdx) },
      ),
    );
  };

  // ── CSV import / export ───────────────────────────────────────────────────

  const handleExportMapping = () => {
    if (!mappedGroups.length) return;
    downloadCsv(buildMappingCsvRows(mappedGroups), "mapping_kodow.csv");
  };

  const handleImportMapping = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = (ev.target?.result as string) ?? "";
      const parsed = parseMappingCsv(text);
      if (parsed.length) setMappedGroups(parsed);
    };
    reader.readAsText(file, "utf-8");
    e.target.value = "";
  };

  const handleImportPrices = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPricesFilename(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = (ev.target?.result as string) ?? "";
      setPrices(parsePricesCsv(text));
    };
    reader.readAsText(file, "utf-8");
    e.target.value = "";
  };

  // ── Preview codes ─────────────────────────────────────────────────────────

  const selectedProducts = useMemo(
    () => allProducts.filter((p) => selectedIds.has(p.product_id)),
    [allProducts, selectedIds],
  );

  interface PreviewRow {
    base: string;
    code: string;
    price: number | null;
  }

  const previewRows = useMemo<PreviewRow[]>(() => {
    if (!mappedGroups.length) return [];
    const rows: PreviewRow[] = [];
    for (const prod of selectedProducts.slice(0, 5)) {
      const lists = mappedGroups.map((g) => g.values.map((v) => v.suffix).filter(Boolean));
      const combos = cartesian(lists);
      for (const combo of combos) {
        const code = [prod.code, ...combo].join("-");
        const price = prices[code.toUpperCase()] ?? null;
        rows.push({ base: prod.code, code, price });
      }
    }
    return rows;
  }, [selectedProducts, mappedGroups, prices]);

  const totalCombos = useMemo(() => {
    if (!mappedGroups.length) return 0;
    return mappedGroups.reduce((acc, g) => acc * Math.max(g.values.filter((v) => v.suffix).length, 1), 1);
  }, [mappedGroups]);

  const pricesLoaded = Object.keys(prices).length;

  // ── Apply job ─────────────────────────────────────────────────────────────

  const startApply = async () => {
    if (!selectedProducts.length || !mappedGroups.length) return;
    setStartError(null);
    setJob(null);

    const optionGroups: OptionGroupConfig[] = mappedGroups.map((g) => ({
      group_id: g.group_id,
      role: g.role,
      values: g.values.filter((v) => v.suffix).map((v) => ({
        value_id: v.value_id,
        suffix: v.suffix,
      })),
    }));

    try {
      const res = await api.startApplyCodes({
        store_id: 1,
        product_ids: selectedProducts.map((p) => p.product_id),
        option_groups: optionGroups,
        prices,
        create_missing: true,
      });
      setJobId(res.job_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Błąd uruchamiania zadania");
    }
  };

  // Poll regular job status
  useEffect(() => {
    if (!jobId) return;
    const poll = async () => {
      try {
        const j = await api.getApplyCodesJob(jobId);
        setJob(j);
        if (j.status === "done") {
          if (pollRef.current) window.clearInterval(pollRef.current);
        }
      } catch {
        // ignore poll errors
      }
    };
    void poll();
    pollRef.current = window.setInterval(poll, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [jobId]);

  const startSupplement = async () => {
    if (!selectedProducts.length || !mappedGroups.length) return;
    setSuppStartError(null);
    setSuppJob(null);

    const optionGroups: OptionGroupConfig[] = mappedGroups.map((g) => ({
      group_id: g.group_id,
      role: g.role,
      values: g.values.filter((v) => v.suffix).map((v) => ({
        value_id: v.value_id,
        suffix: v.suffix,
      })),
    }));

    try {
      const res = await api.startApplyCodes({
        store_id: 1,
        product_ids: selectedProducts.map((p) => p.product_id),
        option_groups: optionGroups,
        prices,
        create_missing: true,
        supplement_mode: true,
      });
      setSuppJobId(res.job_id);
    } catch (e) {
      setSuppStartError(e instanceof Error ? e.message : "Błąd uruchamiania dogenerowania");
    }
  };

  // Poll supplement job status
  useEffect(() => {
    if (!suppJobId) return;
    const poll = async () => {
      try {
        const j = await api.getApplyCodesJob(suppJobId);
        setSuppJob(j);
        if (j.status === "done") {
          if (suppPollRef.current) window.clearInterval(suppPollRef.current);
        }
      } catch {
        // ignore
      }
    };
    void poll();
    suppPollRef.current = window.setInterval(poll, 2000);
    return () => {
      if (suppPollRef.current) window.clearInterval(suppPollRef.current);
    };
  }, [suppJobId]);

  // ── Step state ────────────────────────────────────────────────────────────
  const step1done = selectedGroup !== null;
  const step2done = selectedIds.size > 0;
  const step3done = mappedGroups.length > 0 && mappedGroups.every((g) => g.values.some((v) => v.suffix));
  const step4done = job?.status === "done";

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-900">Wypełnianie kodów wariantów</h2>
        <p className="text-sm text-slate-500 mt-1">
          Wybierz grupę, produkty, zmapuj opcje do suffixów kodu, a następnie zastosuj w Shoperze.
        </p>
      </div>

      <div className="space-y-4">

        {/* ── STEP 1: Group ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
            <StepBadge n={1} active={!step1done} done={step1done} />
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-800">Wybierz zestaw wariantów</p>
              {selectedGroup ? (
                <p className="text-xs font-medium mt-0.5 flex items-center gap-1 min-w-0">
                  <TruncateTooltip text={selectedGroup.name} className="text-indigo-600" />
                  <span className="text-indigo-400 font-normal shrink-0">· {groupSubtitle(selectedGroup)}</span>
                </p>
              ) : (
                <p className="text-xs text-slate-400 mt-0.5">Wybierz grupę aby załadować produkty</p>
              )}
            </div>
            {groupSyncing && (
              <span className="text-xs text-slate-500 flex items-center gap-1.5">
                <span className="w-3 h-3 border-2 border-slate-300 border-t-indigo-500 rounded-full animate-spin" />
                Synchronizuję zestaw…
              </span>
            )}
            {selectedGroup && (
              <button
                type="button"
                onClick={() => {
                  setSelectedGroup(null);
                  setAllProducts([]);
                  setSelectedIds(new Set());
                  setMappedGroups([]);
                  setPendingPoolValue({});
                  setJobId(null);
                  setJob(null);
                }}
                className="text-xs text-slate-400 hover:text-slate-700 transition-colors"
              >
                Zmień
              </button>
            )}
          </div>

          {!selectedGroup && (
            <div className="p-4">
              <input
                type="text"
                value={groupSearch}
                onChange={(e) => setGroupSearch(e.target.value)}
                placeholder="Szukaj zestawu wariantów…"
                className="w-full mb-3 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
              {groupsLoading ? (
                <p className="text-sm text-slate-400 py-4 text-center">Ładuję nazwy zestawów…</p>
              ) : filteredGroups.length === 0 ? (
                <p className="text-sm text-slate-400 py-6 text-center">Brak danych — uruchom pełną synchronizację</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-[300px] overflow-y-auto">
                  {filteredGroups.map((grp) => (
                    <button
                      key={grp.group_id}
                      type="button"
                      onClick={() => void selectGroup(grp)}
                      disabled={groupSyncing}
                      className="flex flex-col items-start gap-0.5 rounded-lg border border-slate-200 px-3 py-2.5 text-left hover:border-indigo-300 hover:bg-indigo-50 transition-colors disabled:opacity-50"
                    >
                      <TruncateTooltip text={grp.name} className="text-sm font-medium text-slate-800" />
                      <span className="text-xs text-slate-400">{groupSubtitle(grp)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {groupSyncError && selectedGroup && (
            <div className="mx-4 mb-4 text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
              {groupSyncError} — wyświetlam dane z lokalnej bazy.
            </div>
          )}
        </div>

        {/* ── STEP 2: Products ───────────────────────────────────────────── */}
        {selectedGroup && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
              <StepBadge n={2} active={step1done && !step2done} done={step2done} />
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-800">Wybierz produkty</p>
                {step2done ? (
                  <p className="text-xs text-indigo-600 font-medium mt-0.5">
                    Zaznaczono {selectedIds.size} {selectedIds.size === 1 ? "produkt" : "produktów"}
                  </p>
                ) : groupSyncing ? (
                  <p className="text-xs text-slate-500 mt-0.5">Odświeżam listę ze Shopera…</p>
                ) : (
                  <p className="text-xs text-slate-400 mt-0.5">Zaznacz produkty do uzupełnienia</p>
                )}
              </div>
            </div>

            <div className="p-4">
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  placeholder="Filtruj po kodzie lub nazwie…"
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
                {filteredProducts.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors whitespace-nowrap"
                  >
                    {selectedIds.size === filteredProducts.length ? "Odznacz wszystkie" : "Zaznacz wszystkie"}
                  </button>
                )}
              </div>

              {prodsLoading ? (
                <p className="text-sm text-slate-400 py-6 text-center">Ładuję produkty…</p>
              ) : filteredProducts.length === 0 ? (
                <p className="text-sm text-slate-400 py-6 text-center">Brak produktów</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5 max-h-[360px] overflow-y-auto">
                  {filteredProducts.map((p) => {
                    const isSelected = selectedIds.has(p.product_id);
                    return (
                      <label
                        key={p.product_id}
                        className={`flex items-start gap-2.5 p-2.5 rounded-lg cursor-pointer border transition-colors ${
                          isSelected
                            ? "bg-indigo-50 border-indigo-200"
                            : "border-transparent hover:bg-slate-50 hover:border-slate-200"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleProduct(p)}
                          className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-mono font-semibold text-slate-900 truncate">{p.code}</p>
                          <p className="text-[11px] text-slate-500 truncate">{p.name}</p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── STEP 3: Option mapping ─────────────────────────────────────── */}
        {step2done && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
              <StepBadge n={3} active={step2done && !step3done} done={step3done} />
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-800">Mapowanie opcji → suffixów kodu</p>
                {mappedGroups.length > 0 ? (
                  <p className="text-xs text-indigo-600 font-medium mt-0.5">
                    {mappedGroups.length} {mappedGroups.length === 1 ? "grupa opcji" : "grupy opcji"},{" "}
                    {totalCombos} kombinacji / produkt
                  </p>
                ) : (
                  <p className="text-xs text-slate-400 mt-0.5">
                    {selectedIds.size > 1
                      ? `Wykryj wspólne grupy opcji dla ${selectedIds.size} zaznaczonych produktów (przecięcie), następnie zmapuj wartości do suffixów`
                      : "Wykryj opcje z zaznaczonego produktu, następnie zmapuj wartości do suffixów"}
                  </p>
                )}
              </div>

              <div className="flex gap-2 shrink-0">
                {/* Import mapping CSV */}
                <input
                  ref={mappingFileRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={handleImportMapping}
                />
                {mappedGroups.length > 0 && (
                  <button
                    type="button"
                    onClick={handleExportMapping}
                    className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
                    title="Eksportuj mapowanie do CSV"
                  >
                    Zapisz mapping
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => mappingFileRef.current?.click()}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
                  title="Wczytaj mapowanie z CSV"
                >
                  Wczytaj mapping
                </button>
                <button
                  type="button"
                  onClick={() => void detectOptions()}
                  disabled={detecting}
                  className="px-4 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
                >
                  {detecting && (
                    <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  )}
                  {detecting ? "Wykrywam…" : selectedIds.size > 1 ? `Wykryj wspólne opcje (${selectedIds.size} prod.)` : "Wykryj opcje z Shopera"}
                </button>
              </div>
            </div>

            {detectError && (
              <div className="mx-4 mt-4 text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                {detectError}
              </div>
            )}

            {mappedGroups.length > 0 && (
              <div className="p-4 space-y-4">
                {/* Prices CSV */}
                <div className="flex items-center gap-3 bg-slate-50 rounded-lg px-3 py-2.5">
                  <input
                    ref={priceFileRef}
                    type="file"
                    accept=".csv,text/csv,.txt"
                    className="hidden"
                    onChange={handleImportPrices}
                  />
                  <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-700">Ceny z CSV</p>
                    {pricesFilename ? (
                      <p className="text-[11px] text-emerald-600 truncate">
                        {pricesFilename} — {pricesLoaded} kodów
                      </p>
                    ) : (
                      <p className="text-[11px] text-slate-400">
                        Wczytaj CSV z kolumnami: kod;cena — dopasowuje ceny do wariantów
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => priceFileRef.current?.click()}
                    className="px-3 py-1 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-colors whitespace-nowrap"
                  >
                    {pricesFilename ? "Zmień" : "Wczytaj ceny"}
                  </button>
                </div>

                {/* Group cards */}
                {mappedGroups.map((group, gIdx) => (
                  <div key={group.group_id} className="border border-slate-200 rounded-lg overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-200">
                      {/* Move up/down */}
                      <div className="flex flex-col gap-0.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => moveGroup(gIdx, -1)}
                          disabled={gIdx === 0}
                          className="text-slate-400 hover:text-slate-700 disabled:opacity-30 p-0.5"
                        >
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => moveGroup(gIdx, 1)}
                          disabled={gIdx === mappedGroups.length - 1}
                          className="text-slate-400 hover:text-slate-700 disabled:opacity-30 p-0.5"
                        >
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                      </div>

                      <span className="text-xs font-mono text-slate-500 shrink-0">#{gIdx + 1}</span>
                      <span className="text-xs font-semibold text-slate-700 flex-1">
                        Grupa opcji {group.group_id}
                      </span>

                      {/* Role selector */}
                      <select
                        value={group.role}
                        onChange={(e) => updateRole(gIdx, e.target.value)}
                        className="text-[11px] rounded border border-slate-200 px-1.5 py-0.5 bg-white text-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-300"
                      >
                        <option value="size">Rozmiar</option>
                        <option value="fabric">Tkanina</option>
                        <option value="other">Inne</option>
                      </select>
                      <RoleBadge role={group.role} />
                    </div>

                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left px-3 py-1.5 text-[11px] font-semibold text-slate-500 w-8">#</th>
                          <th className="text-left px-3 py-1.5 text-[11px] font-semibold text-slate-500">Wartość opcji</th>
                          <th className="text-left px-3 py-1.5 text-[11px] font-semibold text-slate-500 w-32">Suffix w kodzie</th>
                          <th className="w-8"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.values.map((v, vIdx) => (
                          <tr key={v.value_id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50">
                            <td className="px-3 py-1.5 text-[11px] text-slate-400 font-mono">{v.value_id}</td>
                            <td className="px-3 py-1.5 text-xs text-slate-700">{v.value_name}</td>
                            <td className="px-3 py-1.5">
                              <input
                                type="text"
                                value={v.suffix}
                                onChange={(e) => updateSuffix(gIdx, vIdx, e.target.value)}
                                placeholder="np. AA"
                                className="w-full rounded border border-slate-200 px-2 py-0.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-300 placeholder:text-slate-300"
                              />
                            </td>
                            <td className="px-2 py-1.5 text-center">
                              <button
                                type="button"
                                onClick={() => removeValue(gIdx, vIdx)}
                                title="Usuń wartość z listy"
                                className="text-slate-300 hover:text-rose-500 transition-colors"
                              >
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {/* Add from full pool — values not (yet) common to every selected product */}
                    {(() => {
                      const usedIds = new Set(group.values.map((v) => v.value_id));
                      const remaining = group.available.filter((v) => !usedIds.has(v.value_id));
                      if (!remaining.length) return null;
                      return (
                        <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-t border-slate-200">
                          <span className="text-[11px] text-slate-500 shrink-0">Dodaj z całej puli:</span>
                          <select
                            value={pendingPoolValue[gIdx] ?? ""}
                            onChange={(e) =>
                              setPendingPoolValue((prev) => ({ ...prev, [gIdx]: e.target.value }))
                            }
                            className="flex-1 min-w-0 text-xs rounded border border-slate-200 px-2 py-1 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-300"
                          >
                            <option value="">— wybierz wartość ({remaining.length}) —</option>
                            {remaining.map((v) => (
                              <option key={v.value_id} value={v.value_id}>
                                {v.value_name} (id: {v.value_id})
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => addValueFromPool(gIdx)}
                            disabled={!pendingPoolValue[gIdx]}
                            className="px-3 py-1 text-xs font-medium rounded-lg border border-indigo-200 bg-white text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:hover:bg-white transition-colors whitespace-nowrap"
                          >
                            + Dodaj
                          </button>
                        </div>
                      );
                    })()}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── STEP 4: Preview + Apply ────────────────────────────────────── */}
        {step3done && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
              <StepBadge n={4} active={!step4done} done={step4done} />
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-800">Podgląd i zastosowanie</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {selectedProducts.length} produktów × {totalCombos} kombinacji ={" "}
                  <strong>{selectedProducts.length * totalCombos}</strong> wariantów łącznie
                  {pricesLoaded > 0 && (
                    <span className="ml-1 text-emerald-600">({pricesLoaded} cen z CSV)</span>
                  )}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => void startSupplement()}
                  disabled={!!suppJobId && suppJob?.status !== "done"}
                  title="Uzupełnia kody dla wariantów w panelu. Dla produktów z dodatkowymi grupami opcji (spoza panelu) naprawia istniejące kody bez tworzenia nowych."
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                >
                  {suppJobId && suppJob?.status !== "done" ? (
                    <>
                      <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      Dogeneruje…
                    </>
                  ) : (
                    "Dogeneruj"
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void startApply()}
                  disabled={!!jobId && job?.status !== "done"}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                >
                  {jobId && job?.status !== "done" ? (
                    <>
                      <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      Trwa…
                    </>
                  ) : (
                    "Zastosuj kody w Shoper"
                  )}
                </button>
              </div>
            </div>

            <div className="p-4 space-y-4">
              {startError && (
                <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                  {startError}
                </p>
              )}
              {suppStartError && (
                <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                  {suppStartError}
                </p>
              )}

              {/* Supplement job progress */}
              {suppJob && (
                <div className="border border-emerald-200 rounded-lg overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-2 bg-emerald-50 border-b border-emerald-100">
                    <span className="text-xs font-semibold text-emerald-700">Dogeneruj</span>
                    <div className="flex-1">
                      <ProgressBar value={suppJob.done} max={Math.max(suppJob.total, suppJob.done, 1)} />
                    </div>
                    <span className="text-xs text-slate-500 shrink-0 tabular-nums">
                      {suppJob.done} / {suppJob.total || "?"}
                    </span>
                    <span
                      className={`text-xs font-semibold shrink-0 ${
                        suppJob.status === "done" ? "text-emerald-600" : "text-emerald-500"
                      }`}
                    >
                      {suppJob.status === "done" ? "Gotowe" : "W toku…"}
                    </span>
                  </div>
                  <div className="flex gap-6 px-4 py-2 text-xs border-b border-slate-100">
                    <span className="text-emerald-600 font-medium">OK: {suppJob.ok}</span>
                    <span className="text-slate-500">Pominięto: {suppJob.skip}</span>
                    {suppJob.err > 0 && (
                      <span className="text-rose-600 font-medium">Błędy: {suppJob.err}</span>
                    )}
                  </div>
                  <div className="max-h-40 overflow-y-auto p-3 font-mono text-[11px] text-slate-600 space-y-0.5">
                    {suppJob.log.slice(-60).map((line, i) => (
                      <div
                        key={i}
                        className={
                          line.startsWith("ERR") || line.startsWith("FATAL")
                            ? "text-rose-600"
                            : line.startsWith("SKIP")
                            ? "text-slate-400"
                            : "text-emerald-700"
                        }
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Live job progress */}
              {job && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 border-b border-slate-200">
                    <span className="text-xs font-semibold text-slate-600">Zastosuj kody</span>
                    <div className="flex-1">
                      <ProgressBar value={job.done} max={Math.max(job.total, job.done, 1)} />
                    </div>
                    <span className="text-xs text-slate-500 shrink-0 tabular-nums">
                      {job.done} / {job.total || "?"}
                    </span>
                    <span
                      className={`text-xs font-semibold shrink-0 ${
                        job.status === "done" ? "text-emerald-600" : "text-indigo-600"
                      }`}
                    >
                      {job.status === "done" ? "Gotowe" : "W toku…"}
                    </span>
                  </div>
                  <div className="flex gap-6 px-4 py-2 text-xs border-b border-slate-100">
                    <span className="text-emerald-600 font-medium">OK: {job.ok}</span>
                    <span className="text-slate-500">Pominięto: {job.skip}</span>
                    {job.err > 0 && (
                      <span className="text-rose-600 font-medium">Błędy: {job.err}</span>
                    )}
                  </div>
                  <div className="max-h-40 overflow-y-auto p-3 font-mono text-[11px] text-slate-600 space-y-0.5">
                    {job.log.slice(-60).map((line, i) => (
                      <div
                        key={i}
                        className={
                          line.startsWith("ERR") || line.startsWith("FATAL")
                            ? "text-rose-600"
                            : line.startsWith("SKIP")
                            ? "text-slate-400"
                            : "text-emerald-700"
                        }
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Code preview (first 5 products) */}
              {previewRows.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-slate-500 mb-2 uppercase tracking-wide">
                    Podgląd kodów (pierwsze {Math.min(selectedProducts.length, 5)} produktów)
                  </p>
                  <div className="space-y-3">
                    {selectedProducts.slice(0, 5).map((prod) => {
                      const rows = previewRows.filter((r) => r.base === prod.code);
                      if (!rows.length) return null;
                      return (
                        <div key={prod.product_id}>
                          <p className="text-[11px] font-mono font-medium text-slate-600 mb-1.5">
                            {prod.code} — {prod.name}
                          </p>
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
                            {rows.map((r) => (
                              <div
                                key={r.code}
                                className="flex items-center justify-between rounded-md px-2.5 py-1.5 bg-slate-50 border border-slate-100"
                              >
                                <span
                                  className="text-[11px] font-mono text-slate-700 truncate"
                                  title={r.code}
                                >
                                  {r.code}
                                </span>
                                {r.price !== null && (
                                  <span className="text-[10px] text-emerald-600 font-medium ml-1 shrink-0">
                                    {r.price.toFixed(0)} zł
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                    {selectedProducts.length > 5 && (
                      <p className="text-xs text-slate-400 text-center">
                        … i {selectedProducts.length - 5} więcej produktów (podgląd skrócony)
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
