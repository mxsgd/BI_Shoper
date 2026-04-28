import { useEffect, useState, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { api } from "../api";
import type { OverviewData, RevenueData, TrafficData, TrackerEventSummary } from "../api";
import { FocusBanner } from "../components/FocusBanner";
import { LineHitDot } from "../components/ChartHitDot";

function KpiCard({ title, value, delta, prefix = "", suffix = "", deltaHint }: {
  title: string; value: string | number; delta: number | null; prefix?: string; suffix?: string;
  deltaHint?: string;
}) {
  const color = delta === null ? "text-slate-400" : delta >= 0 ? "text-emerald-600" : "text-red-500";
  const arrow = delta === null ? "" : delta >= 0 ? "\u2191" : "\u2193";
  const deltaLabel = deltaHint ?? "vs poprzedni okres";
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className="text-2xl font-bold mt-1">{prefix}{typeof value === "number" ? value.toLocaleString("pl-PL") : value}{suffix}</p>
      {delta !== null && (
        <p className={`text-sm mt-1 font-medium ${color}`}>
          {arrow} {Math.abs(delta)}% {deltaLabel}
        </p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [revenue, setRevenue] = useState<RevenueData | null>(null);
  const [trafficData, setTrafficData] = useState<TrafficData | null>(null);
  const [tracker, setTracker] = useState<TrackerEventSummary | null>(null);
  const [period, setPeriod] = useState(30);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const isFirstFetch = useRef(true);

  const toggleDate = (d: string) => setSelectedDate((prev) => (prev === d ? null : d));
  const clearSelection = () => setSelectedDate(null);

  const setPeriodAndClear = (p: number) => {
    clearSelection();
    setPeriod(p);
  };

  useEffect(() => {
    const fd = selectedDate ?? undefined;
    if (isFirstFetch.current) setLoading(true);
    Promise.all([
      api.overview(period, fd),
      api.revenue(period, "day", fd),
      api.traffic(period, fd),
      api.tracker(7),
    ])
      .then(([o, r, t, tr]) => {
        setOverview(o);
        setRevenue(r);
        setTrafficData(t);
        setTracker(tr);
      })
      .finally(() => {
        setLoading(false);
        isFirstFetch.current = false;
      });
  }, [period, selectedDate]);

  if (loading && !revenue) return <Loader />;
  if (!overview || !revenue) return <p>Brak danych</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Dashboard</h2>
          <p className="text-sm text-slate-500">
            {overview.date_from} — {overview.date_to}
            {selectedDate ? (
              <span className="ml-2 text-indigo-600 font-medium">· KPI i tabele: wybrany dzień</span>
            ) : null}
          </p>
        </div>
        <PeriodSelector value={period} onChange={setPeriodAndClear} />
      </div>

      <FocusBanner
        selectedDate={selectedDate}
        onClear={clearSelection}
        subtitle="KPI, tabele statusów/kanałów i metryki GA4 dotyczą wybranej daty."
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard title="Przychód" value={overview.revenue} delta={overview.revenue_delta_pct} suffix=" zł" deltaHint={overview.focus_date ? "vs poprzedni dzień" : undefined} />
        <KpiCard title="Zamówienia" value={overview.orders} delta={overview.orders_delta_pct} deltaHint={overview.focus_date ? "vs poprzedni dzień" : undefined} />
        <KpiCard title="Śr. wartość (AOV)" value={overview.aov} delta={overview.aov_delta_pct} suffix=" zł" deltaHint={overview.focus_date ? "vs poprzedni dzień" : undefined} />
        <KpiCard title="Klienci" value={overview.customers} delta={overview.customers_delta_pct} deltaHint={overview.focus_date ? "vs poprzedni dzień" : undefined} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-1">Przychód w czasie</h3>
          <p className="text-xs text-slate-400 mb-3">Kliknij linię przychodu lub słupek zamówień, aby zawęzić tabele poniżej (bez przeładowania wykresu).</p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={revenue.time_series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString("pl-PL")} zł`} />
              <Line
                type="monotone"
                dataKey="revenue"
                stroke="#6366f1"
                strokeWidth={2}
                name="Przychód"
                dot={(props) => LineHitDot(props, selectedDate, toggleDate)}
                activeDot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Zamówienia / dzień</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={revenue.time_series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar
                dataKey="orders"
                radius={[4, 4, 0, 0]}
                name="Zamówienia"
                onClick={(item: { payload?: { date?: string } }) => {
                  const dt = item?.payload?.date;
                  if (typeof dt === "string") toggleDate(dt);
                }}
              >
                {revenue.time_series.map((entry) => (
                  <Cell
                    key={entry.date}
                    fill={selectedDate === entry.date ? "#4f46e5" : "#8b5cf6"}
                    style={{ cursor: "pointer" }}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Wg statusu</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th className="pb-2">Status</th><th className="pb-2 text-right">Zamówienia</th><th className="pb-2 text-right">Przychód</th></tr></thead>
            <tbody>
              {revenue.by_status.map((s) => (
                <tr key={s.status} className="border-t border-slate-50">
                  <td className="py-1.5">{s.status || "—"}</td>
                  <td className="py-1.5 text-right">{s.orders}</td>
                  <td className="py-1.5 text-right font-medium">{s.revenue.toLocaleString("pl-PL")} zł</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Kanały sprzedaży</h3>
          {revenue.by_channel.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={revenue.by_channel} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <YAxis type="category" dataKey="channel" tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString("pl-PL")} zł`} />
                <Bar dataKey="revenue" fill="#8b5cf6" radius={[0, 4, 4, 0]} name="Przychód" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate-400">Brak danych o kanałach</p>
          )}
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Dodatkowe KPI</h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Śr. produktów/zamówienie</span><span className="font-medium">{overview.avg_items_per_order}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">% opłaconych</span><span className="font-medium">{overview.paid_pct}%</span></div>
            {trafficData?.has_data && trafficData.conversion && (
              <>
                <div className="flex justify-between">
                  <span className="text-slate-500">Konwersja (GA4)</span>
                  <span className="font-medium text-indigo-600">{trafficData.conversion.conversion_rate}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Sesje (GA4)</span>
                  <span className="font-medium">{trafficData.conversion.sessions.toLocaleString("pl-PL")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Przychód/sesja</span>
                  <span className="font-medium">{trafficData.conversion.revenue_per_session.toLocaleString("pl-PL")} zł</span>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Tracker (ostatnie 7 dni)</h3>
          {tracker && tracker.total_events > 0 ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">Wszystkie eventy</span>
                <span className="font-medium">{tracker.total_events.toLocaleString("pl-PL")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Unikalni użytkownicy</span>
                <span className="font-medium">{tracker.distinct_users.toLocaleString("pl-PL")}</span>
              </div>
              {tracker.by_event.slice(0, 3).map((e) => (
                <div key={e.event_name} className="flex justify-between">
                  <span className="text-slate-500 truncate max-w-[60%]" title={e.event_name}>{e.event_name}</span>
                  <span className="font-medium">{e.count.toLocaleString("pl-PL")}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Brak eventów trackera w ostatnich 7 dniach.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function PeriodSelector({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
      {[7, 30, 90, 365].map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            value === d ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {d === 365 ? "1Y" : `${d}D`}
        </button>
      ))}
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
