import { useEffect, useState } from "react";
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend, Line, ComposedChart,
} from "recharts";
import { api } from "../api";
import type { TrendsData } from "../api";
import { FocusBanner } from "../components/FocusBanner";
import { LineHitDot } from "../components/ChartHitDot";

const WEEKDAYS = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Ndz"];

export default function Trends() {
  const [data, setData] = useState<TrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const toggleDate = (d: string) => setSelectedDate((prev) => (prev === d ? null : d));
  const clearSelection = () => setSelectedDate(null);

  useEffect(() => {
    setLoading(true);
    api.trends(365).then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;
  if (!data) return <p>Brak danych</p>;

  const selDay = selectedDate ? data.daily.find((d) => d.date === selectedDate) : undefined;

  const lastMonth = data.monthly[data.monthly.length - 1];
  const prevMonth = data.monthly.length > 1 ? data.monthly[data.monthly.length - 2] : null;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">Trendy sprzedaży</h2>
      <p className="text-sm text-slate-500 mb-4">Analiza trendów, średnie kroczące i porównania okresowe</p>

      <FocusBanner
        selectedDate={selectedDate}
        onClear={clearSelection}
        subtitle="Wyróżnienie na wykresie — karty u góry nadal za cały okres API (365 dni)."
      />

      {/* MoM Growth Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <GrowthCard
          title="Przychód (ost. miesiąc)"
          value={lastMonth ? `${lastMonth.revenue.toLocaleString("pl-PL")} zł` : "—"}
          delta={lastMonth?.mom_growth_pct}
          label="MoM"
        />
        <GrowthCard
          title="Zamówienia (ost. miesiąc)"
          value={lastMonth ? lastMonth.orders.toLocaleString("pl-PL") : "—"}
          delta={prevMonth && lastMonth ? round((lastMonth.orders - prevMonth.orders) / (prevMonth.orders || 1) * 100) : null}
          label="MoM"
        />
        <GrowthCard
          title="Przychód YoY"
          value={lastMonth ? `${lastMonth.revenue.toLocaleString("pl-PL")} zł` : "—"}
          delta={lastMonth?.yoy_growth_pct}
          label="YoY"
        />
        <GrowthCard
          title="Śr. dzienna (MA30)"
          value={data.daily.length > 0 ? `${data.daily[data.daily.length - 1].ma30.toLocaleString("pl-PL")} zł` : "—"}
          delta={null}
          label=""
        />
      </div>

      {/* Revenue with Moving Averages */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">Przychód dzienny + średnie kroczące</h3>
        <p className="text-xs text-slate-400 mb-3">Kliknij dzień, aby go wyróżnić (porównanie z resztą serii).</p>
        {selDay ? (
          <p className="text-sm text-indigo-800 mb-3">
            <strong className="tabular-nums">{selDay.date}</strong>
            {" · "}
            {selDay.revenue.toLocaleString("pl-PL")} zł, {selDay.orders} zamówień
          </p>
        ) : null}
        <ResponsiveContainer width="100%" height={350}>
          <ComposedChart data={data.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
            <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString("pl-PL")} zł`} />
            <Legend />
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
            <Line
              type="monotone"
              dataKey="ma7"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name="MA7"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="ma30"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              name="MA30"
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Monthly Table */}
        <div className="lg:col-span-2 bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Porównanie miesięczne</h3>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">Miesiąc</th>
                  <th className="pb-2 text-right">Przychód</th>
                  <th className="pb-2 text-right">Zamówienia</th>
                  <th className="pb-2 text-right">MoM %</th>
                  <th className="pb-2 text-right">YoY %</th>
                </tr>
              </thead>
              <tbody>
                {[...data.monthly].reverse().map((m) => (
                  <tr key={m.month} className="border-t border-slate-50">
                    <td className="py-1.5">{m.month.slice(0, 7)}</td>
                    <td className="py-1.5 text-right font-medium">{m.revenue.toLocaleString("pl-PL")} zł</td>
                    <td className="py-1.5 text-right">{m.orders}</td>
                    <td className="py-1.5 text-right">
                      {m.mom_growth_pct !== null ? <DeltaBadge value={m.mom_growth_pct} /> : "—"}
                    </td>
                    <td className="py-1.5 text-right">
                      {m.yoy_growth_pct !== null ? <DeltaBadge value={m.yoy_growth_pct} /> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Weekday Pattern */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Wzorzec tygodniowy</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.weekday_pattern.map((w) => ({ ...w, name: WEEKDAYS[w.day_of_week - 1] }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString("pl-PL")} zł`} />
              <Bar dataKey="avg_revenue" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Śr. przychód" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function GrowthCard({ title, value, delta, label }: {
  title: string; value: string; delta: number | null; label: string;
}) {
  const color = delta === null ? "text-slate-400" : delta >= 0 ? "text-emerald-600" : "text-red-500";
  const arrow = delta === null ? "" : delta >= 0 ? "\u2191" : "\u2193";
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className="text-xl font-bold mt-1">{value}</p>
      {delta !== null && (
        <p className={`text-sm mt-1 font-medium ${color}`}>
          {arrow} {Math.abs(delta)}% {label}
        </p>
      )}
    </div>
  );
}

function DeltaBadge({ value }: { value: number }) {
  const color = value >= 0 ? "text-emerald-600 bg-emerald-50" : "text-red-600 bg-red-50";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${color}`}>
      {value >= 0 ? "+" : ""}{value}%
    </span>
  );
}

function round(v: number) {
  return Math.round(v * 10) / 10;
}

function Loader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}
