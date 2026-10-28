import { useEffect, useState, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { api } from "../api";
import type { RevenueData } from "../api";
import { FocusBanner } from "../components/FocusBanner";
import { LineHitDot } from "../components/ChartHitDot";
import { t, locale } from "../i18n";

const COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#e0e7ff", "#f59e0b", "#10b981", "#ef4444"];

type BreakdownRow = { label: string; orders: number; revenue: number; quantity?: number };

export default function Orders() {
  const [data, setData] = useState<RevenueData | null>(null);
  const [period, setPeriod] = useState(30);
  const [groupBy, setGroupBy] = useState<"day" | "week" | "month">("day");
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const isFirstFetch = useRef(true);

  const toggleDate = (d: string) => setSelectedDate((prev) => (prev === d ? null : d));
  const clearSelection = () => setSelectedDate(null);

  const focusForApi = groupBy === "day" ? selectedDate ?? undefined : undefined;

  useEffect(() => {
    if (isFirstFetch.current) setLoading(true);
    api.revenue(period, groupBy, focusForApi)
      .then(setData)
      .finally(() => {
        setLoading(false);
        isFirstFetch.current = false;
      });
  }, [period, groupBy, focusForApi]);

  if (loading && !data) return <Loader />;
  if (!data) return <p>{t("Brak danych", "No data")}</p>;

  const row =
    selectedDate && groupBy === "day"
      ? data.time_series.find((p) => p.date === selectedDate)
      : null;
  const totalOrders = row ? row.orders : data.time_series.reduce((s, p) => s + p.orders, 0);
  const totalRevenue = row ? row.revenue : data.time_series.reduce((s, p) => s + p.revenue, 0);

  const statusRows: BreakdownRow[] = data.by_status.map((s) => ({
    label: s.status || "—",
    orders: s.orders,
    revenue: s.revenue,
  }));
  const categoryRows: BreakdownRow[] = (data.by_category ?? []).map((c) => ({
    label: c.category,
    orders: c.orders,
    revenue: c.revenue,
    quantity: c.quantity,
  }));

  return (
    <div>
      <FocusBanner
        selectedDate={selectedDate}
        onClear={clearSelection}
        subtitle={t("Szczegóły statusów i kategorii dotyczą wybranej daty (tylko widok dzienny).", "Status and category details refer to the selected date (daily view only).")}
      />
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">{t("Zamówienia", "Orders")}</h2>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {([
            { value: 7, label: "7D", group: "day" },
            { value: 30, label: "30D", group: "day" },
            { value: 90, label: "90D", group: "week" },
            { value: 365, label: "1Y", group: "month" },
          ] as const).map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                clearSelection();
                setPeriod(opt.value);
                setGroupBy(opt.group);
              }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                period === opt.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Stat label={t("Zamówienia", "Orders")} value={totalOrders} />
        <Stat label={t("Przychód", "Revenue")} value={`${totalRevenue.toLocaleString(locale)} zł`} />
        <Stat label={t("Śr./dzień", "Avg./day")} value={(totalOrders / Math.max(data.time_series.length, 1)).toFixed(1)} />
        <Stat label={t("Śr. wartość", "Avg. value")} value={`${totalOrders ? (totalRevenue / totalOrders).toFixed(0) : 0} zł`} />
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">{t("Przychód i zamówienia w czasie", "Revenue and orders over time")}</h3>
        <p className="text-xs text-slate-400 mb-3">
          {groupBy === "day"
            ? t("Kliknij punkt, aby zawęzić szczegóły statusów i kategorii do tego dnia.", "Click a point to narrow status and category details to that day.")
            : t("Przełącz na widok dzienny (7D / 30D), aby wybierać konkretny dzień.", "Switch to the daily view (7D / 30D) to pick a specific day.")}
        </p>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data.time_series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis yAxisId="rev" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
            <YAxis yAxisId="ord" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v, name) => (name === t("Przychód", "Revenue") ? `${Number(v ?? 0).toLocaleString(locale)} zł` : v)} />
            <Line
              yAxisId="rev"
              type="monotone"
              dataKey="revenue"
              stroke="#6366f1"
              strokeWidth={2}
              name={t("Przychód", "Revenue")}
              dot={groupBy === "day" ? (props) => LineHitDot(props, selectedDate, toggleDate) : false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="ord"
              type="monotone"
              dataKey="orders"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name={t("Zamówienia", "Orders")}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <BreakdownSection
          title={t("Przychód wg statusu", "Revenue by status")}
          labelHeader="Status"
          rows={statusRows}
          chartLimit={statusRows.length}
        />
        <BreakdownSection
          title={t("Przychód wg kategorii", "Revenue by category")}
          labelHeader={t("Kategoria", "Category")}
          rows={categoryRows}
          chartLimit={15}
          showQuantity
          emptyMessage={t("Brak danych o kategoriach w wybranym okresie.", "No category data in the selected period.")}
        />
      </div>
    </div>
  );
}

function BreakdownSection({
  title,
  labelHeader,
  rows,
  chartLimit,
  showQuantity = false,
  emptyMessage = t("Brak danych w wybranym okresie.", "No data in the selected period."),
}: {
  title: string;
  labelHeader: string;
  rows: BreakdownRow[];
  chartLimit: number;
  showQuantity?: boolean;
  emptyMessage?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const chartRows = rows.slice(0, chartLimit);
  const chartHeight = Math.max(220, Math.min(chartRows.length, chartLimit) * 32);

  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
      <h3 className="text-sm font-semibold text-slate-700 mb-4">{title}</h3>

      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">{emptyMessage}</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={chartRows} layout="vertical" margin={{ left: 8, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 11 }}
                width={110}
                tickFormatter={(v) => (v.length > 16 ? `${v.slice(0, 16)}…` : v || "—")}
              />
              <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString(locale)} zł`} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]} name={t("Przychód", "Revenue")}>
                {chartRows.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-4 flex w-full items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <span>
              {expanded ? t("Ukryj szczegóły", "Hide details") : t("Pokaż szczegóły", "Show details")}
              <span className="ml-2 text-slate-400">({rows.length} {t("pozycji", "rows")})</span>
            </span>
            <Chevron open={expanded} />
          </button>

          {expanded && (
            <div className="mt-3 overflow-x-auto max-h-[420px] overflow-y-auto rounded-lg border border-slate-100">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="text-left text-slate-500">
                    <th className="px-3 py-2">{labelHeader}</th>
                    <th className="px-3 py-2 text-right">{t("Zam.", "Orders")}</th>
                    {showQuantity && <th className="px-3 py-2 text-right">{t("Szt.", "Qty")}</th>}
                    <th className="px-3 py-2 text-right">{t("Przychód", "Revenue")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label} className="border-t border-slate-50">
                      <td className="px-3 py-1.5 max-w-xs truncate" title={r.label}>{r.label}</td>
                      <td className="px-3 py-1.5 text-right">{r.orders}</td>
                      {showQuantity && <td className="px-3 py-1.5 text-right">{r.quantity ?? 0}</td>}
                      <td className="px-3 py-1.5 text-right font-medium">{r.revenue.toLocaleString(locale)} zł</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-4 w-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden
    >
      <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
    </svg>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100">
      <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
      <p className="text-xl font-bold mt-1">{value}</p>
    </div>
  );
}

function Loader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}
