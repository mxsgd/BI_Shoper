import { useEffect, useState, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from "recharts";
import { api } from "../api";
import type { TrafficData } from "../api";
import { FocusBanner } from "../components/FocusBanner";
import { LineHitDot } from "../components/ChartHitDot";
import { t, lang, locale } from "../i18n";

const DEVICE_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

function deviceLabel(category: string): string {
  const map: Record<string, string> = {
    mobile: "Mobile",
    desktop: "Desktop",
    tablet: "Tablet",
    "smart tv": "Smart TV",
  };
  return map[category.toLowerCase()] ?? category;
}

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
  if (!data) return <p>{t("Brak danych", "No data")}</p>;

  if (!data.has_data) {
    return (
      <div>
        <h2 className="text-2xl font-bold mb-1">{t("Ruch na stronie", "Site traffic")}</h2>
        <div className="mt-8 bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <p className="text-amber-800 font-medium">{t("Brak danych GA4 w wybranym okresie", "No GA4 data in the selected period")}</p>
          <p className="text-sm text-amber-600 mt-1">
            {lang === "pl" ? (
              <>
                Ustaw GA4_PROPERTY_ID i GA4_CREDENTIALS_PATH w backend/.env, zainstaluj{" "}
                <code className="text-xs">google-analytics-data</code> w venv, a następnie kliknij „Odśwież”
                (szybkie odświeżenie pobiera też dane GA4).
              </>
            ) : (
              <>
                Set GA4_PROPERTY_ID and GA4_CREDENTIALS_PATH in backend/.env, install{" "}
                <code className="text-xs">google-analytics-data</code> in the venv, then click “Refresh”
                (a quick refresh pulls GA4 data too).
              </>
            )}
          </p>
          {data.data_through && (
            <p className="text-xs text-amber-500 mt-2">{t("Ostatnie dane w bazie", "Latest data in the database")}: {data.data_through}</p>
          )}
        </div>
      </div>
    );
  }

  const dataLagDays = data.data_through
    ? Math.floor((Date.now() - new Date(data.data_through + "T12:00:00").getTime()) / 86400000)
    : null;
  const dataStale = dataLagDays !== null && dataLagDays > 1;

  const ov = data.overview!;
  const conv = data.conversion!;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">{t("Ruch na stronie", "Site traffic")}</h2>
          <p className="text-sm text-slate-500">
            {t("Dane z Google Analytics 4 + konwersja Shoper", "Google Analytics 4 data + Shoper conversion")}
            {data.data_through && (
              <span className="text-slate-400"> · {t("dane do", "data through")} {data.data_through}</span>
            )}
          </p>
        </div>
        <PeriodSelector value={period} onChange={setPeriodAndClear} />
      </div>

      {dataStale && (
        <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          {lang === "pl"
            ? `Dane GA4 są nieaktualne (ostatni dzień: ${data.data_through}). Kliknij „Odśwież” w menu — szybkie odświeżenie pobiera też ruch z GA4.`
            : `GA4 data is stale (last day: ${data.data_through}). Click “Refresh” in the menu; a quick refresh pulls GA4 traffic too.`}
        </div>
      )}

      <FocusBanner
        selectedDate={selectedDate}
        onClear={clearSelection}
        subtitle={t("KPI, lejek, źródła ruchu i tabele dotyczą wybranej daty.", "KPIs, funnel, sources and tables refer to the selected date.")}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <KpiCard title={t("Sesje", "Sessions")} value={ov.sessions.toLocaleString(locale)} />
        <KpiCard title={t("Użytkownicy", "Users")} value={ov.users.toLocaleString(locale)} />
        <KpiCard title="Bounce Rate" value={`${(ov.bounce_rate * 100).toFixed(1)}%`} />
        <KpiCard title={t("Śr. czas sesji", "Avg. session time")} value={formatDuration(ov.avg_session_duration)} />
        <KpiCard title={t("Konwersja", "Conversion")} value={`${conv.conversion_rate}%`} accent />
      </div>

      {/* Simple Conversion Funnel */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">{t("Lejek konwersji (sesje → zamówienia)", "Conversion funnel (sessions → orders)")}</h3>
        <div className="flex items-center gap-3">
          <FunnelStep label={t("Sesje", "Sessions")} value={conv.sessions} pct={100} />
          <Arrow />
          <FunnelStep label={t("Zamówienia", "Orders")} value={conv.orders} pct={conv.conversion_rate} />
          <Arrow />
          <FunnelStep label={t("Przychód", "Revenue")} value={`${conv.revenue.toLocaleString(locale)} zł`} pct={null} />
          <div className="ml-auto text-sm text-slate-500">
            {t("Przychód/sesja", "Revenue/session")}: <span className="font-semibold text-slate-800">{conv.revenue_per_session.toLocaleString(locale)} zł</span>
          </div>
        </div>
      </div>

      {/* Sessions vs Orders Chart */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">{t("Sesje vs Zamówienia", "Sessions vs orders")}</h3>
        <p className="text-xs text-slate-400 mb-3">{t("Kliknij linię „Sesje” przy wybranym dniu, aby zawęzić metryki i tabele.", "Click the Sessions line on a day to narrow metrics and tables.")}</p>
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
              name={t("Sesje", "Sessions")}
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
              name={t("Zamówienia", "Orders")}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Geographic */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Geografia", "Geography")}</h3>
          <div className="overflow-auto max-h-64">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">{t("Kraj", "Country")}</th>
                  <th className="pb-2">{t("Miasto", "City")}</th>
                  <th className="pb-2 text-right">{t("Sesje", "Sessions")}</th>
                  <th className="pb-2 text-right">{t("Użytk.", "Users")}</th>
                </tr>
              </thead>
              <tbody>
                {data.geo.map((g, i) => (
                  <tr key={i} className="border-t border-slate-50">
                    <td className="py-1.5">{g.country}</td>
                    <td className="py-1.5 text-slate-600">{g.city}</td>
                    <td className="py-1.5 text-right">{g.sessions.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">{g.users.toLocaleString(locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Device Split */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Urządzenia", "Devices")}</h3>
          {data.devices.length > 0 ? (
            <div className="overflow-visible">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <Pie
                    data={data.devices}
                    dataKey="sessions"
                    nameKey="device_category"
                    cx="50%"
                    cy="45%"
                    innerRadius={48}
                    outerRadius={78}
                    label={false}
                  >
                    {data.devices.map((_, i) => (
                      <Cell key={i} fill={DEVICE_COLORS[i % DEVICE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v, _name, item) => {
                      const d = item.payload as { device_category: string; pct: number };
                      return [
                        `${Number(v ?? 0).toLocaleString(locale)} ${t("sesji", "sessions")} (${d.pct}%)`,
                        deviceLabel(d.device_category),
                      ];
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    align="center"
                    wrapperStyle={{ paddingTop: 12 }}
                    formatter={(value, entry) => {
                      const d = entry.payload as { device_category: string; pct: number; sessions: number };
                      return `${deviceLabel(d.device_category)} — ${d.pct}%`;
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-slate-400">{t("Brak danych", "No data")}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Traffic Sources */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Źródła ruchu", "Traffic sources")}</h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">{t("Źródło / Medium", "Source / Medium")}</th>
                  <th className="pb-2 text-right">{t("Sesje", "Sessions")}</th>
                  <th className="pb-2 text-right">{t("Użytk.", "Users")}</th>
                  <th className="pb-2 text-right">{t("Konw.", "Conv.")}</th>
                </tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={`${s.source}-${s.medium}`} className="border-t border-slate-50">
                    <td className="py-1.5">
                      <span className="font-medium">{s.source}</span>
                      <span className="text-slate-400"> / {s.medium}</span>
                    </td>
                    <td className="py-1.5 text-right">{s.sessions.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">{s.users.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">{s.conversions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Top Pages */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Najpopularniejsze strony", "Top pages")}</h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">{t("Ścieżka", "Path")}</th>
                  <th className="pb-2 text-right">{t("Wyśw.", "Views")}</th>
                  <th className="pb-2 text-right">{t("Śr. czas", "Avg. time")}</th>
                  <th className="pb-2 text-right">{t("Wejścia", "Entrances")}</th>
                </tr>
              </thead>
              <tbody>
                {data.top_pages.map((p) => (
                  <tr key={p.page_path} className="border-t border-slate-50">
                    <td className="py-1.5 font-mono text-xs truncate max-w-48" title={p.page_path}>{p.page_path}</td>
                    <td className="py-1.5 text-right">{p.views.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">{formatDuration(p.avg_time)}</td>
                    <td className="py-1.5 text-right">{p.entrances}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
      <p className="text-lg font-bold">{typeof value === "number" ? value.toLocaleString(locale) : value}</p>
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
