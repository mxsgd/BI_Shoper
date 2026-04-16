import { useEffect, useState, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from "recharts";
import { api } from "../api";
import type { TrafficData, TrafficFunnel } from "../api";
import { FocusBanner } from "../components/FocusBanner";
import { LineHitDot } from "../components/ChartHitDot";

const DEVICE_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

const PERIODS = [
  { value: 7, label: "7D" },
  { value: 30, label: "30D" },
  { value: 90, label: "90D" },
  { value: 365, label: "1Y" },
];

export default function Traffic() {
  const [data, setData] = useState<TrafficData | null>(null);
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
    if (isFirstFetch.current) setLoading(true);
    api.traffic(period, selectedDate ?? undefined)
      .then(setData)
      .finally(() => {
        setLoading(false);
        isFirstFetch.current = false;
      });
  }, [period, selectedDate]);

  if (loading && !data) return <Loader />;
  if (!data) return <p>Brak danych</p>;

  if (!data.has_data) {
    return (
      <div>
        <h2 className="text-2xl font-bold mb-1">Ruch na stronie</h2>
        <div className="mt-8 bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <p className="text-amber-800 font-medium">Brak danych GA4</p>
          <p className="text-sm text-amber-600 mt-1">
            Ustaw GA4_PROPERTY_ID i GA4_CREDENTIALS_PATH w .env, a następnie uruchom synchronizację
            (POST /api/stores/sync-now z scope="ga4").
          </p>
        </div>
      </div>
    );
  }

  const ov = data.overview!;
  const conv = data.conversion!;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Ruch na stronie</h2>
          <p className="text-sm text-slate-500">Dane z Google Analytics 4 + konwersja Shoper</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriodAndClear} />
      </div>

      <FocusBanner
        selectedDate={selectedDate}
        onClear={clearSelection}
        subtitle="KPI, lejek, źródła ruchu i tabele dotyczą wybranej daty."
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <KpiCard title="Sesje" value={ov.sessions.toLocaleString("pl-PL")} />
        <KpiCard title="Użytkownicy" value={ov.users.toLocaleString("pl-PL")} />
        <KpiCard title="Bounce Rate" value={`${(ov.bounce_rate * 100).toFixed(1)}%`} />
        <KpiCard title="Śr. czas sesji" value={formatDuration(ov.avg_session_duration)} />
        <KpiCard title="Konwersja" value={`${conv.conversion_rate}%`} accent />
      </div>

      {/* Simple Conversion Funnel */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Lejek konwersji (sesje → zamówienia)</h3>
        <div className="flex items-center gap-3">
          <FunnelStep label="Sesje" value={conv.sessions} pct={100} />
          <Arrow />
          <FunnelStep label="Zamówienia" value={conv.orders} pct={conv.conversion_rate} />
          <Arrow />
          <FunnelStep label="Przychód" value={`${conv.revenue.toLocaleString("pl-PL")} zł`} pct={null} />
          <div className="ml-auto text-sm text-slate-500">
            Przychód/sesja: <span className="font-semibold text-slate-800">{conv.revenue_per_session.toLocaleString("pl-PL")} zł</span>
          </div>
        </div>
      </div>

      {/* Extended Sales Funnel */}
      {data.funnel && data.funnel.view_item > 0 && (
        <ExtendedFunnel funnel={data.funnel} />
      )}

      {/* Sessions vs Orders Chart */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">Sesje vs Zamówienia</h3>
        <p className="text-xs text-slate-400 mb-3">Kliknij linię „Sesje” przy wybranym dniu, aby zawęzić metryki i tabele.</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data.time_series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="sessions"
              stroke="#6366f1"
              strokeWidth={2}
              name="Sesje"
              dot={(props) => LineHitDot(props, selectedDate, toggleDate)}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="orders"
              stroke="#10b981"
              strokeWidth={2}
              name="Zamówienia"
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Traffic Sources */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Źródła ruchu</h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">Źródło / Medium</th>
                  <th className="pb-2 text-right">Sesje</th>
                  <th className="pb-2 text-right">Użytk.</th>
                  <th className="pb-2 text-right">Konw.</th>
                </tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={`${s.source}-${s.medium}`} className="border-t border-slate-50">
                    <td className="py-1.5">
                      <span className="font-medium">{s.source}</span>
                      <span className="text-slate-400"> / {s.medium}</span>
                    </td>
                    <td className="py-1.5 text-right">{s.sessions.toLocaleString("pl-PL")}</td>
                    <td className="py-1.5 text-right">{s.users.toLocaleString("pl-PL")}</td>
                    <td className="py-1.5 text-right">{s.conversions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Top Pages */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Najpopularniejsze strony</h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">Ścieżka</th>
                  <th className="pb-2 text-right">Wyśw.</th>
                  <th className="pb-2 text-right">Śr. czas</th>
                  <th className="pb-2 text-right">Wejścia</th>
                </tr>
              </thead>
              <tbody>
                {data.top_pages.map((p) => (
                  <tr key={p.page_path} className="border-t border-slate-50">
                    <td className="py-1.5 font-mono text-xs truncate max-w-48" title={p.page_path}>{p.page_path}</td>
                    <td className="py-1.5 text-right">{p.views.toLocaleString("pl-PL")}</td>
                    <td className="py-1.5 text-right">{formatDuration(p.avg_time)}</td>
                    <td className="py-1.5 text-right">{p.entrances}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Geographic */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Geografia</h3>
          <div className="overflow-auto max-h-64">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">Kraj</th>
                  <th className="pb-2">Miasto</th>
                  <th className="pb-2 text-right">Sesje</th>
                  <th className="pb-2 text-right">Użytk.</th>
                </tr>
              </thead>
              <tbody>
                {data.geo.map((g, i) => (
                  <tr key={i} className="border-t border-slate-50">
                    <td className="py-1.5">{g.country}</td>
                    <td className="py-1.5 text-slate-600">{g.city}</td>
                    <td className="py-1.5 text-right">{g.sessions.toLocaleString("pl-PL")}</td>
                    <td className="py-1.5 text-right">{g.users.toLocaleString("pl-PL")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Device Split */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Urządzenia</h3>
          {data.devices.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={data.devices}
                  dataKey="sessions"
                  nameKey="device_category"
                  cx="50%" cy="50%"
                  innerRadius={50} outerRadius={90}
                  label={(props: { payload?: { device_category?: string; pct?: number }; device_category?: string; pct?: number }) => {
                    const p = props.payload ?? props;
                    return `${p.device_category ?? ""} ${p.pct ?? 0}%`;
                  }}
                >
                  {data.devices.map((_, i) => (
                    <Cell key={i} fill={DEVICE_COLORS[i % DEVICE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => Number(v ?? 0).toLocaleString("pl-PL")} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate-400">Brak danych</p>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value, accent = false }: { title: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-xl p-5 shadow-sm border ${accent ? "bg-indigo-50 border-indigo-200" : "bg-white border-slate-100"}`}>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className={`text-xl font-bold mt-1 ${accent ? "text-indigo-700" : ""}`}>{value}</p>
    </div>
  );
}

function FunnelStep({ label, value, pct }: { label: string; value: string | number; pct: number | null }) {
  return (
    <div className="text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-lg font-bold">{typeof value === "number" ? value.toLocaleString("pl-PL") : value}</p>
      {pct !== null && <p className="text-xs text-slate-400">{pct}%</p>}
    </div>
  );
}

function Arrow() {
  return <div className="text-slate-300 text-xl">&rarr;</div>;
}

function PeriodSelector({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
      {PERIODS.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            value === p.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

const FUNNEL_STEPS: { key: keyof TrafficFunnel; label: string; color: string }[] = [
  { key: "view_item", label: "Wyświetlenia produktu", color: "#6366f1" },
  { key: "add_to_cart", label: "Dodania do koszyka", color: "#8b5cf6" },
  { key: "begin_checkout", label: "Wejście do checkout", color: "#f59e0b" },
  { key: "add_payment_info", label: "Płatność rozpoczęta", color: "#f97316" },
  { key: "purchase", label: "Zakup", color: "#10b981" },
];

function ExtendedFunnel({ funnel }: { funnel: TrafficFunnel }) {
  const maxVal = funnel.view_item || 1;

  const chartData = FUNNEL_STEPS.map((s) => ({
    name: s.label,
    value: funnel[s.key] as number,
    fill: s.color,
  }));

  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
      <h3 className="text-sm font-semibold text-slate-700 mb-1">Lejek sprzedażowy (rozszerzony)</h3>
      <p className="text-xs text-slate-400 mb-5">Dane z GA4 e-commerce events — szczegóły w zakładce Koszyk</p>

      <div className="space-y-3 mb-6">
        {FUNNEL_STEPS.map((step, i) => {
          const val = funnel[step.key] as number;
          const pct = maxVal > 0 ? val / maxVal * 100 : 0;
          const prevVal = i > 0 ? (funnel[FUNNEL_STEPS[i - 1].key] as number) : null;
          const dropPct = prevVal && prevVal > 0 ? round((1 - val / prevVal) * 100) : null;
          return (
            <div key={step.key} className="flex items-center gap-3">
              <div className="w-44 text-sm text-slate-600 text-right shrink-0">{step.label}</div>
              <div className="flex-1 relative h-9">
                <div
                  className="h-full rounded-md flex items-center transition-all"
                  style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: step.color }}
                >
                  <span className="text-white text-xs font-semibold ml-2 whitespace-nowrap">
                    {val.toLocaleString("pl-PL")}
                  </span>
                </div>
              </div>
              <div className="w-16 text-right text-xs tabular-nums text-slate-500">{round(pct)}%</div>
              <div className="w-20 text-right text-xs tabular-nums">
                {dropPct !== null && dropPct > 0 ? (
                  <span className="text-red-500">-{dropPct}%</span>
                ) : dropPct !== null ? (
                  <span className="text-emerald-500">0%</span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
          <Tooltip formatter={(v) => Number(v ?? 0).toLocaleString("pl-PL")} />
          <Bar dataKey="value" name="Zdarzenia" radius={[4, 4, 0, 0]}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function round(v: number) {
  return Math.round(v * 10) / 10;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function Loader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}
