import { useEffect, useState } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { api } from "../api";
import type { TopProductsData } from "../api";

export default function Products() {
  const [data, setData] = useState<TopProductsData | null>(null);
  const [period, setPeriod] = useState(90);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.topProducts(period, 20).then(setData).finally(() => setLoading(false));
  }, [period]);

  if (loading) return <Loader />;
  if (!data) return <p>Brak danych</p>;

  const chartData = data.products.map((p, i) => ({
    name: p.name.length > 25 ? p.name.slice(0, 25) + "…" : p.name,
    revenue: p.revenue,
    cumulative: p.cumulative_pct,
    idx: i + 1,
  }));

  const totalRevenue = data.products.reduce((s, p) => s + p.revenue, 0);
  const totalQty = data.products.reduce((s, p) => s + p.quantity, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Produkty — Top 20</h2>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <Stat label="Przychód (top 20)" value={`${totalRevenue.toLocaleString("pl-PL")} zł`} />
        <Stat label="Sprzedanych szt." value={totalQty} />
        <Stat label="Pareto 80%" value={`${data.products.filter((p) => p.cumulative_pct <= 80).length} produktów`} />
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Analiza Pareto (przychód + krzywa kumulacyjna)</h3>
        <ResponsiveContainer width="100%" height={350}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="idx" tick={{ fontSize: 11 }} label={{ value: "Produkt #", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis yAxisId="rev" tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
            <YAxis yAxisId="pct" orientation="right" tick={{ fontSize: 11 }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip formatter={(v, name) =>
              name === "Przychód"
                ? `${Number(v ?? 0).toLocaleString("pl-PL")} zł`
                : `${Number(v ?? 0).toFixed(1)}%`
            } />
            <Legend />
            <Bar yAxisId="rev" dataKey="revenue" fill="#6366f1" radius={[4, 4, 0, 0]} name="Przychód" />
            <Line yAxisId="pct" dataKey="cumulative" stroke="#f59e0b" strokeWidth={2} dot={false} name="Kumulacyjny %" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Ranking produktów</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="pb-2 pr-4">#</th>
                <th className="pb-2 pr-4">Produkt</th>
                <th className="pb-2 pr-4">Kategoria</th>
                <th className="pb-2 pr-4 text-right">Szt.</th>
                <th className="pb-2 pr-4 text-right">Przychód</th>
                <th className="pb-2 pr-4 text-right">%</th>
                <th className="pb-2 text-right">Kumulat. %</th>
              </tr>
            </thead>
            <tbody>
              {data.products.map((p, i) => (
                <tr key={p.product_id} className={`border-t border-slate-50 ${p.cumulative_pct <= 80 ? "" : "text-slate-400"}`}>
                  <td className="py-2 pr-4">{i + 1}</td>
                  <td className="py-2 pr-4 max-w-xs truncate font-medium">{p.name}</td>
                  <td className="py-2 pr-4 text-slate-500">{p.category || "—"}</td>
                  <td className="py-2 pr-4 text-right">{p.quantity}</td>
                  <td className="py-2 pr-4 text-right font-medium">{p.revenue.toLocaleString("pl-PL")} zł</td>
                  <td className="py-2 pr-4 text-right">{p.revenue_pct}%</td>
                  <td className="py-2 text-right">{p.cumulative_pct.toFixed(1)}%</td>
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

function PeriodSelector({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
      {[30, 90, 180, 365].map((d) => (
        <button key={d} onClick={() => onChange(d)}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${value === d ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
        >{d === 365 ? "1Y" : `${d}D`}</button>
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
