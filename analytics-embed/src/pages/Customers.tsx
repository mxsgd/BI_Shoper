import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { api } from "../api";
import type { CustomersData } from "../api";
import { t, locale } from "../i18n";

const PIE_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444"];

export default function Customers() {
  const [data, setData] = useState<CustomersData | null>(null);
  const [period, setPeriod] = useState(90);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.customers(period).then(setData).finally(() => setLoading(false));
  }, [period]);

  if (loading) return <Loader />;
  if (!data) return <p>{t("Brak danych", "No data")}</p>;

  const segPie = data.segmentation.map((s) => ({
    name: s.type === "returning" ? t("Powracający", "Returning") : t("Nowi", "New"),
    value: s.count,
  }));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">{t("Klienci", "Customers")}</h2>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat label={t("Kupujący łącznie", "Total buyers")} value={data.retention.total_buyers} />
        <Stat label={t("Powracający", "Returning")} value={data.retention.repeat_buyers} />
        <Stat label={t("Jednorazowi", "One-time")} value={data.retention.one_time_buyers} />
        <Stat label={t("Wskaźnik retencji", "Repeat rate")} value={`${data.retention.repeat_rate_pct}%`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">{t("Segmentacja", "Segmentation")}</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={segPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                {segPie.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="lg:col-span-2 bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">{t("Nowi klienci miesięcznie", "New customers per month")}</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.new_customers_monthly}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(0, 7)} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name={t("Nowi klienci", "New customers")} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Segmenty — szczegóły", "Segments — details")}</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="pb-2">{t("Typ", "Type")}</th>
                <th className="pb-2 text-right">{t("Ilość", "Count")}</th>
                <th className="pb-2 text-right">{t("Przychód", "Revenue")}</th>
                <th className="pb-2 text-right">{t("Śr. zamów.", "Avg. orders")}</th>
                <th className="pb-2 text-right">{t("Śr. przych.", "Avg. revenue")}</th>
              </tr>
            </thead>
            <tbody>
              {data.segmentation.map((s) => (
                <tr key={s.type} className="border-t border-slate-50">
                  <td className="py-1.5 font-medium">{s.type === "returning" ? t("Powracający", "Returning") : t("Nowi", "New")}</td>
                  <td className="py-1.5 text-right">{s.count}</td>
                  <td className="py-1.5 text-right">{s.revenue.toLocaleString(locale)} zł</td>
                  <td className="py-1.5 text-right">{s.avg_orders}</td>
                  <td className="py-1.5 text-right">{s.avg_revenue.toLocaleString(locale)} zł</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Top klienci (przychód)", "Top customers (revenue)")}</h3>
          <div className="overflow-y-auto max-h-72">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="pb-2">#</th>
                  <th className="pb-2 text-right">{t("Zamówienia", "Orders")}</th>
                  <th className="pb-2 text-right">{t("Przychód", "Revenue")}</th>
                  <th className="pb-2 text-right">{t("Ostatnie", "Last order")}</th>
                </tr>
              </thead>
              <tbody>
                {data.top_customers.slice(0, 15).map((c, i) => (
                  <tr key={c.customer_id} className="border-t border-slate-50">
                    <td className="py-1.5">{i + 1}</td>
                    <td className="py-1.5 text-right">{c.total_orders}</td>
                    <td className="py-1.5 text-right font-medium">{c.total_revenue.toLocaleString(locale)} zł</td>
                    <td className="py-1.5 text-right text-slate-500">{c.last_order || "—"}</td>
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
