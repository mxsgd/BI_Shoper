import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { api } from "../api";
import type { RevenueData } from "../api";

const COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#e0e7ff", "#f59e0b", "#10b981", "#ef4444"];

export default function Orders() {
  const [data, setData] = useState<RevenueData | null>(null);
  const [period, setPeriod] = useState(30);
  const [groupBy, setGroupBy] = useState<"day" | "week" | "month">("day");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.revenue(period, groupBy).then(setData).finally(() => setLoading(false));
  }, [period, groupBy]);

  if (loading) return <Loader />;
  if (!data) return <p>Brak danych</p>;

  const totalOrders = data.time_series.reduce((s, p) => s + p.orders, 0);
  const totalRevenue = data.time_series.reduce((s, p) => s + p.revenue, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Zamówienia</h2>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {([
            { value: 7, label: "7D", group: "day" },
            { value: 30, label: "30D", group: "day" },
            { value: 90, label: "90D", group: "week" },
            { value: 365, label: "1Y", group: "month" },
          ] as const).map((opt) => (
            <button
              key={opt.value}
              onClick={() => { setPeriod(opt.value); setGroupBy(opt.group); }}
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
        <Stat label="Zamówienia" value={totalOrders} />
        <Stat label="Przychód" value={`${totalRevenue.toLocaleString("pl-PL")} zł`} />
        <Stat label="Śr./dzień" value={(totalOrders / Math.max(data.time_series.length, 1)).toFixed(1)} />
        <Stat label="Śr. wartość" value={`${totalOrders ? (totalRevenue / totalOrders).toFixed(0) : 0} zł`} />
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Przychód i zamówienia w czasie</h3>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data.time_series}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis yAxisId="rev" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
            <YAxis yAxisId="ord" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: number, name: string) => name === "Przychód" ? `${v.toLocaleString("pl-PL")} zł` : v} />
            <Line yAxisId="rev" type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={2} dot={false} name="Przychód" />
            <Line yAxisId="ord" type="monotone" dataKey="orders" stroke="#f59e0b" strokeWidth={2} dot={false} name="Zamówienia" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Przychód wg statusu</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.by_status} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <YAxis type="category" dataKey="status" tick={{ fontSize: 11 }} width={120} tickFormatter={(v) => v || "—"} />
              <Tooltip formatter={(v: number) => `${v.toLocaleString("pl-PL")} zł`} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]} name="Przychód">
                {data.by_status.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Szczegóły statusów</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500"><th className="pb-2">Status</th><th className="pb-2 text-right">Ilość</th><th className="pb-2 text-right">Przychód</th></tr></thead>
            <tbody>
              {data.by_status.map((s) => (
                <tr key={s.status} className="border-t border-slate-50">
                  <td className="py-1.5">{s.status || "—"}</td>
                  <td className="py-1.5 text-right">{s.orders}</td>
                  <td className="py-1.5 text-right font-medium">{s.revenue.toLocaleString("pl-PL")} zł</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
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
