import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../api";
import type { CohortData, RfmData } from "../api";

const SEGMENT_COLORS: Record<string, string> = {
  "Mistrzowie": "#10b981",
  "Lojalni": "#3b82f6",
  "Nowi klienci": "#8b5cf6",
  "Zagrożeni": "#f59e0b",
  "Utraceni": "#ef4444",
  "Inni": "#94a3b8",
};

export default function Retention() {
  const [cohortData, setCohortData] = useState<CohortData | null>(null);
  const [rfmData, setRfmData] = useState<RfmData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.cohorts(12), api.rfm()])
      .then(([c, r]) => { setCohortData(c); setRfmData(r); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;
  if (!cohortData || !rfmData) return <p>Brak danych</p>;

  const maxOffset = Math.max(0, ...cohortData.cohorts.flatMap((c) => c.months.map((m) => m.month_offset)));

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">Retencja i segmentacja</h2>
      <p className="text-sm text-slate-500 mb-6">Analiza kohortowa, RFM i wartość życiowa klienta</p>

      {/* CLV Summary Cards */}
      {rfmData.summary.total_customers > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <SummaryCard title="Klienci (z zamówieniami)" value={rfmData.summary.total_customers.toLocaleString("pl-PL")} />
          <SummaryCard title="Śr. CLV" value={`${rfmData.summary.avg_clv.toLocaleString("pl-PL")} zł`} />
          <SummaryCard title="Łączny przychód" value={`${rfmData.summary.total_revenue.toLocaleString("pl-PL")} zł`} />
        </div>
      )}

      {/* RFM Segment Cards */}
      <div className="mb-8">
        <h3 className="text-lg font-semibold mb-4">Segmenty RFM</h3>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          {rfmData.segments.map((seg) => (
            <div
              key={seg.name}
              className="rounded-xl p-4 border shadow-sm"
              style={{ borderLeftWidth: 4, borderLeftColor: SEGMENT_COLORS[seg.name] || "#94a3b8" }}
            >
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{seg.name}</p>
              <p className="text-2xl font-bold mt-1">{seg.count}</p>
              <div className="mt-2 space-y-0.5 text-xs text-slate-500">
                <p>Śr. przychód: <span className="font-medium text-slate-700">{seg.avg_revenue.toLocaleString("pl-PL")} zł</span></p>
                <p>Śr. zamówienia: <span className="font-medium text-slate-700">{seg.avg_orders}</span></p>
                <p>Śr. recencja: <span className="font-medium text-slate-700">{seg.avg_recency_days} dni</span></p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* RFM Segment Chart */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-8">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Rozkład segmentów</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={rfmData.segments} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={110} />
            <Tooltip formatter={(v: number) => v.toLocaleString("pl-PL")} />
            <Bar dataKey="count" name="Liczba klientów" radius={[0, 4, 4, 0]}>
              {rfmData.segments.map((seg) => (
                <Cell key={seg.name} fill={SEGMENT_COLORS[seg.name] || "#94a3b8"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Cohort Retention Heatmap */}
      {cohortData.cohorts.length > 0 && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Macierz retencji kohortowej</h3>
          <div className="overflow-x-auto">
            <table className="text-xs w-full">
              <thead>
                <tr>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">Kohorta</th>
                  <th className="text-center py-2 px-1 text-slate-500 font-medium">Rozmiar</th>
                  {Array.from({ length: Math.min(maxOffset + 1, 13) }, (_, i) => (
                    <th key={i} className="text-center py-2 px-1 text-slate-500 font-medium">M{i}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cohortData.cohorts.map((cohort) => {
                  const monthMap = Object.fromEntries(cohort.months.map((m) => [m.month_offset, m]));
                  return (
                    <tr key={cohort.cohort_month} className="border-t border-slate-100">
                      <td className="py-1.5 px-2 font-medium text-slate-700">{cohort.cohort_month.slice(0, 7)}</td>
                      <td className="py-1.5 px-1 text-center text-slate-600">{cohort.size}</td>
                      {Array.from({ length: Math.min(maxOffset + 1, 13) }, (_, i) => {
                        const entry = monthMap[i];
                        if (!entry) return <td key={i} className="py-1.5 px-1 text-center text-slate-300">—</td>;
                        const pct = entry.retention_pct;
                        return (
                          <td
                            key={i}
                            className="py-1.5 px-1 text-center font-medium"
                            style={{
                              backgroundColor: retentionColor(pct),
                              color: pct > 50 ? "#fff" : "#1e293b",
                            }}
                          >
                            {pct}%
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-400 mt-3">M0 = miesiąc pierwszego zakupu. Wartości pokazują % klientów z kohorty, którzy dokonali zakupu w danym miesiącu.</p>
        </div>
      )}
    </div>
  );
}

function retentionColor(pct: number): string {
  if (pct >= 80) return "#059669";
  if (pct >= 60) return "#10b981";
  if (pct >= 40) return "#34d399";
  if (pct >= 20) return "#6ee7b7";
  if (pct >= 10) return "#a7f3d0";
  if (pct >= 5) return "#d1fae5";
  return "#f1f5f9";
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
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
