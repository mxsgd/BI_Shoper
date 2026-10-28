import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, Legend,
} from "recharts";
import { api } from "../api";
import type { CartData, CartFunnel } from "../api";
import { t, locale } from "../i18n";

const PERIODS = [
  { value: 7, label: "7D" },
  { value: 30, label: "30D" },
  { value: 90, label: "90D" },
  { value: 365, label: "1Y" },
];

const FUNNEL_STEPS: { key: keyof CartFunnel; label: string; color: string }[] = [
  { key: "view_item", label: t("Wyświetlenia produktu", "Product views"), color: "#6366f1" },
  { key: "add_to_cart", label: t("Dodania do koszyka", "Adds to cart"), color: "#8b5cf6" },
  { key: "begin_checkout", label: t("Wejście do checkout", "Checkout started"), color: "#f59e0b" },
  { key: "add_payment_info", label: t("Płatność rozpoczęta", "Payment started"), color: "#f97316" },
  { key: "purchase", label: t("Zakup", "Purchase"), color: "#10b981" },
];

export default function Cart() {
  const [data, setData] = useState<CartData | null>(null);
  const [period, setPeriod] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.cart(period).then(setData).finally(() => setLoading(false));
  }, [period]);

  if (loading) return <Loader />;
  if (!data) return <p>{t("Brak danych", "No data")}</p>;

  const f = data.funnel;
  const om = data.order_metrics;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">{t("Analiza koszyka", "Cart analysis")}</h2>
          <p className="text-sm text-slate-500">{t("Lejek sprzedażowy, porzucenia i metryki zamówień", "Sales funnel, abandonment and order metrics")}</p>
        </div>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* ── KPI Row 1: Funnel rates ── */}
      {f && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <KpiCard
            title="Add-to-cart rate"
            value={pctLabel(f.add_to_cart_rate)}
            desc={t("% sesji → dodanie do koszyka", "% of sessions → add to cart")}
            good={f.add_to_cart_rate > 5}
          />
          <KpiCard
            title="Cart abandonment"
            value={`${f.cart_abandonment_rate}%`}
            desc={t("% koszyków bez zakupu", "% of carts without purchase")}
            good={f.cart_abandonment_rate < 50}
            inverted
          />
          <KpiCard
            title="Checkout abandonment"
            value={`${f.checkout_abandonment_rate}%`}
            desc={t("% checkoutów bez zakupu", "% of checkouts without purchase")}
            good={f.checkout_abandonment_rate < 30}
            inverted
          />
          <KpiCard
            title={t("Śr. wartość koszyka", "Avg. cart value")}
            value={`${f.avg_cart_value.toLocaleString(locale)} zł`}
            desc={`${t("vs zamówienie", "vs order")}: ${om.avg_order_value.toLocaleString(locale)} zł`}
          />
        </div>
      )}

      {/* ── KPI Row 2: Order-based metrics ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KpiCard
          title={t("Śr. wartość zamówienia", "Avg. order value")}
          value={`${om.avg_order_value.toLocaleString(locale)} zł`}
          desc={`${t("z rabatem", "with discount")}: ${om.avg_value_with_discount.toLocaleString(locale)} zł`}
        />
        <KpiCard
          title={t("% zamówień z rabatem", "% orders with discount")}
          value={`${om.discount_pct}%`}
          desc={`${t("bez rabatu", "without discount")}: ${om.avg_value_without_discount.toLocaleString(locale)} zł`}
        />
        <KpiCard
          title={t("1 produkt vs multi", "Single vs multi-item")}
          value={`${om.single_item_pct}% / ${om.multi_item_pct}%`}
          desc={t("jedno- vs wieloproduktowe", "single- vs multi-item orders")}
        />
        <KpiCard
          title={t("Śr. produktów w koszyku", "Avg. items per order")}
          value={`${om.avg_items_per_order}`}
          desc={`${om.total_orders.toLocaleString(locale)} ${t("zamówień w okresie", "orders in period")}`}
        />
      </div>

      {/* ── 1. Funnel visualization ── */}
      {f && f.view_item > 0 && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
          <h3 className="text-sm font-semibold text-slate-700 mb-1">{t("Lejek koszyka", "Cart funnel")}</h3>
          <p className="text-xs text-slate-400 mb-5">{t("View → Add to cart → Checkout → Purchase — gdzie ginie kasa", "View → Add to cart → Checkout → Purchase — where the money drops off")}</p>

          <div className="space-y-3 mb-6 overflow-x-auto">
            {FUNNEL_STEPS.map((step, i) => {
              const val = f[step.key] as number;
              const maxVal = Math.max(
                ...FUNNEL_STEPS.map((s) => Number(f[s.key] || 0)),
                1,
              );
              const pct = (val / maxVal) * 100;
              const pctOfView = ((val / (f.view_item || 1)) * 100);
              const prevVal = i > 0 ? (f[FUNNEL_STEPS[i - 1].key] as number) : null;
              const dropPct = prevVal && prevVal > 0 ? rd((1 - val / prevVal) * 100) : null;
              return (
                <div key={step.key} className="flex items-center gap-3 min-w-[760px]">
                  <div className="w-44 text-sm text-slate-600 text-right shrink-0">{step.label}</div>
                  <div className="flex-1 relative h-9">
                    <div
                      className="h-full rounded-md"
                      style={{ width: `${Math.max(Math.min(pct, 100), 2)}%`, backgroundColor: step.color }}
                    />
                  </div>
                  <div className="w-20 text-right text-xs tabular-nums text-slate-700 font-semibold">
                    {val.toLocaleString(locale)}
                  </div>
                  <div className="w-16 text-right text-xs tabular-nums text-slate-500">{pctLabel(pctOfView)}</div>
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
            {f.remove_from_cart > 0 && (
              <div className="flex items-center gap-3 min-w-[760px]">
                <div className="w-44 text-sm text-slate-600 text-right shrink-0 italic">{t("Usunięcia z koszyka", "Removals from cart")}</div>
                <div className="flex-1 relative h-7">
                  <div
                    className="h-full rounded-md bg-red-400"
                    style={{ width: `${Math.max(f.remove_from_cart / (f.view_item || 1) * 100, 1)}%` }}
                  />
                </div>
                <div className="w-20 text-right text-xs tabular-nums text-slate-700 font-semibold">
                  {f.remove_from_cart.toLocaleString(locale)}
                </div>
                <div className="w-16 text-right text-xs tabular-nums text-slate-500">
                  {pctLabel((f.remove_from_cart / (f.view_item || 1)) * 100)}
                </div>
                <div className="w-20 text-right text-xs tabular-nums text-slate-500">—</div>
              </div>
            )}
          </div>

          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={FUNNEL_STEPS.map((s) => ({ name: s.label, value: f[s.key] as number, fill: s.color }))}
              margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
              <Tooltip formatter={(v) => Number(v ?? 0).toLocaleString(locale)} />
              <Bar dataKey="value" name={t("Zdarzenia", "Events")} radius={[4, 4, 0, 0]}>
                {FUNNEL_STEPS.map((s, i) => (
                  <Cell key={i} fill={s.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* ── 2. Abandoned vs purchased ── */}
        {data.abandoned_vs_purchased.length > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Porzucone vs kupione koszyki", "Abandoned vs purchased carts")}</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.abandoned_vs_purchased} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="purchased" stackId="a" fill="#10b981" name={t("Kupione", "Purchased")} radius={[0, 0, 0, 0]} />
                <Bar dataKey="abandoned" stackId="a" fill="#ef4444" name={t("Porzucone", "Abandoned")} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* ── 3. Items histogram ── */}
        {data.items_histogram.length > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Liczba produktów w zamówieniu", "Items per order")}</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.items_histogram} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="items" tick={{ fontSize: 11 }} label={{ value: t("Produkty", "Items"), position: "insideBottom", offset: -2, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => `${Number(v ?? 0).toLocaleString(locale)} ${t("zamówień", "orders")}`} />
                <Bar dataKey="orders" fill="#8b5cf6" name={t("Zamówienia", "Orders")} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── 4. Top abandoned products ── */}
      {data.top_abandoned_products.length > 0 && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("Najczęściej porzucane produkty", "Most abandoned products")}</h3>
          <div className="overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="pb-2">{t("Produkt", "Product")}</th>
                  <th className="pb-2 text-right">{t("Do koszyka", "Added to cart")}</th>
                  <th className="pb-2 text-right">{t("Zakupy", "Purchases")}</th>
                  <th className="pb-2 text-right">Drop-off</th>
                  <th className="pb-2 text-right">Drop-off %</th>
                  <th className="pb-2 text-right">{t("Przychód", "Revenue")}</th>
                </tr>
              </thead>
              <tbody>
                {data.top_abandoned_products.map((p) => (
                  <tr key={p.name} className="border-t border-slate-50">
                    <td className="py-1.5 max-w-64 truncate" title={p.name}>{p.name}</td>
                    <td className="py-1.5 text-right">{p.add_to_cart.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">{p.purchases.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right text-red-500 font-medium">{p.drop_off.toLocaleString(locale)}</td>
                    <td className="py-1.5 text-right">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                        p.drop_off_pct > 80 ? "text-red-600 bg-red-50" :
                        p.drop_off_pct > 50 ? "text-amber-600 bg-amber-50" :
                        "text-emerald-600 bg-emerald-50"
                      }`}>
                        {p.drop_off_pct}%
                      </span>
                    </td>
                    <td className="py-1.5 text-right">{p.revenue.toLocaleString(locale)} zł</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}

function KpiCard({ title, value, desc, good, inverted = false }: {
  title: string; value: string; desc?: string; good?: boolean; inverted?: boolean;
}) {
  let border = "bg-white border-slate-100";
  let textColor = "";
  if (good !== undefined) {
    border = good
      ? "border-emerald-200 bg-emerald-50"
      : (inverted ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50");
    textColor = good
      ? "text-emerald-700"
      : (inverted ? "text-red-700" : "text-amber-700");
  }
  return (
    <div className={`rounded-xl p-4 shadow-sm border ${border}`}>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{title}</p>
      <p className={`text-xl font-bold mt-1 ${textColor}`}>{value}</p>
      {desc && <p className="text-xs text-slate-400 mt-0.5">{desc}</p>}
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

function rd(v: number) {
  return Math.round(v * 10) / 10;
}

function pctLabel(v: number) {
  if (!Number.isFinite(v)) return "0%";
  if (v > 100) return ">100%";
  return `${rd(v)}%`;
}

function Loader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );
}
