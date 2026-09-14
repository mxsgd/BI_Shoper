import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../api";
import type { TrackerEventSummary } from "../api";

const PERIODS = [
  { value: 1, label: "24H" },
  { value: 7, label: "7D" },
  { value: 30, label: "30D" },
  { value: 90, label: "90D" },
];

const EVENT_COLORS = ["#6366f1", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#0ea5e9", "#f97316", "#14b8a6"];

const EVENT_LABELS: Record<string, string> = {
  page_view: "Wyświetlenie strony",
  click: "Kliknięcie",
  view_item: "Wyświetlenie produktu",
  add_to_cart: "Dodanie do koszyka",
  remove_from_cart: "Usunięcie z koszyka",
  begin_checkout: "Rozpoczęcie checkout",
  checkout_step: "Krok checkout",
  purchase: "Zakup",
};

function eventLabel(name: string): string {
  return EVENT_LABELS[name] ?? name;
}

export default function Tracker() {
  const [data, setData] = useState<TrackerEventSummary | null>(null);
  const [period, setPeriod] = useState(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.tracker(period).then(setData).finally(() => setLoading(false));
  }, [period]);

  if (loading && !data) return <Loader />;
  if (!data) return <p>Brak danych</p>;

  if (data.total_events === 0) {
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold">Tracker</h2>
            <p className="text-sm text-slate-500">Zdarzenia z własnego trackera (tracker_events_local)</p>
          </div>
          <PeriodSelector value={period} onChange={setPeriod} />
        </div>
        <div className="mt-8 bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <p className="text-amber-800 font-medium">Brak eventów trackera w wybranym okresie</p>
          <p className="text-sm text-amber-600 mt-1">
            Sprawdź, czy skrypt trackera jest zainstalowany na stronie sklepu i wysyła zdarzenia do API.
          </p>
        </div>
      </div>
    );
  }

  const eventsPerUser = data.distinct_users > 0 ? data.total_events / data.distinct_users : 0;
  const totalByEvent = data.by_event.reduce((sum, e) => sum + e.count, 0) || 1;
  const totalByUrl = data.top_urls.reduce((sum, u) => sum + u.count, 0) || 1;
  const sinceLabel = new Date(data.since_iso).toLocaleString("pl-PL", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">Tracker</h2>
          <p className="text-sm text-slate-500">
            Zdarzenia z własnego trackera <span className="text-slate-400">· od {sinceLabel}</span>
          </p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard title="Zdarzenia" value={data.total_events.toLocaleString("pl-PL")} />
        <KpiCard title="Unikalni użytkownicy" value={data.distinct_users.toLocaleString("pl-PL")} />
        <KpiCard title="Zdarzeń / użytkownika" value={eventsPerUser.toFixed(1)} />
        <KpiCard title="Typy zdarzeń" value={data.by_event.length.toString()} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Events by type */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Zdarzenia wg typu</h3>
          {data.by_event.length > 0 ? (
            <ResponsiveContainer width="100%" height={Math.max(220, data.by_event.length * 34)}>
              <BarChart
                data={data.by_event}
                layout="vertical"
                margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="event_name"
                  tick={{ fontSize: 11 }}
                  tickFormatter={eventLabel}
                  width={140}
                />
                <Tooltip
                  formatter={(v: number) => [v.toLocaleString("pl-PL"), "Liczba"]}
                  labelFormatter={(l: string) => eventLabel(l)}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {data.by_event.map((_, i) => (
                    <Cell key={i} fill={EVENT_COLORS[i % EVENT_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate-400">Brak danych</p>
          )}
        </div>

        {/* Events by type table */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Rozkład zdarzeń</h3>
          <div className="overflow-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">Zdarzenie</th>
                  <th className="pb-2 text-right">Liczba</th>
                  <th className="pb-2 text-right">%</th>
                </tr>
              </thead>
              <tbody>
                {data.by_event.map((e) => (
                  <tr key={e.event_name} className="border-t border-slate-50">
                    <td className="py-1.5">{eventLabel(e.event_name)}</td>
                    <td className="py-1.5 text-right">{e.count.toLocaleString("pl-PL")}</td>
                    <td className="py-1.5 text-right text-slate-400">
                      {((e.count / totalByEvent) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Top URLs */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Najpopularniejsze adresy URL</h3>
        <div className="overflow-auto max-h-96">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="pb-2">URL</th>
                <th className="pb-2 text-right">Zdarzenia</th>
                <th className="pb-2 text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {data.top_urls.map((u, i) => (
                <tr key={`${u.url}-${i}`} className="border-t border-slate-50">
                  <td className="py-1.5 font-mono text-xs truncate max-w-md" title={u.url}>{u.url}</td>
                  <td className="py-1.5 text-right">{u.count.toLocaleString("pl-PL")}</td>
                  <td className="py-1.5 text-right text-slate-400">
                    {((u.count / totalByUrl) * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
              {data.top_urls.length === 0 && (
                <tr>
                  <td colSpan={3} className="py-4 text-center text-slate-400">Brak danych</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-xl p-5 shadow-sm border bg-white border-slate-100">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className="text-xl font-bold mt-1">{value}</p>
    </div>
  );
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

function Loader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}
