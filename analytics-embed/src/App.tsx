import { useEffect, useRef, useState } from "react";
import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Orders from "./pages/Orders";
import Products from "./pages/Products";
import Customers from "./pages/Customers";
import Trends from "./pages/Trends";
import Retention from "./pages/Retention";
import Traffic from "./pages/Traffic";
import Cart from "./pages/Cart";
import PriceUpdate from "./pages/PriceUpdate";
import VariantCodes from "./pages/VariantCodes";
import { usePageView } from "./usePageView";
import { api } from "./api";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1" },
  { to: "/orders", label: "Zamówienia", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" },
  { to: "/products", label: "Produkty", icon: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" },
  { to: "/customers", label: "Klienci", icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" },
  { to: "/trends", label: "Trendy", icon: "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" },
  { to: "/retention", label: "Retencja", icon: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" },
  { to: "/traffic", label: "Ruch", icon: "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" },
  { to: "/cart", label: "Koszyk", icon: "M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 100 4 2 2 0 000-4z" },
  { to: "/price-update", label: "Aktualizacja cen", icon: "M12 4v16m8-8H4" },
  { to: "/variant-codes", label: "Kody wariantów", icon: "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" },
];

function Sidebar() {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [syncDone, setSyncDone] = useState(false);
  const sawRunningSync = useRef(false);

  useEffect(() => {
    let disposed = false;

    async function loadSyncStatus() {
      try {
        const status = await api.getSyncStatus();
        if (disposed) return;

        const running = status.status === "running";
        setIsRefreshing(running);

        if (running) {
          sawRunningSync.current = true;
          setRefreshError(null);
          setSyncDone(false);
          return;
        }

        if (status.status === "error" && status.error) {
          sawRunningSync.current = false;
          setRefreshError(status.error);
          return;
        }

        if (sawRunningSync.current && status.status === "done") {
          sawRunningSync.current = false;
          setSyncDone(true);
          // Reload page after short delay so user sees the "done" message first
          window.setTimeout(() => window.location.reload(), 1500);
        }
      } catch {
        if (!disposed) setIsRefreshing(false);
      }
    }

    void loadSyncStatus();
    const timer = window.setInterval(() => void loadSyncStatus(), 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const [showFullSync, setShowFullSync] = useState(false);

  async function handleRefresh(scope: "quick" | "all" = "quick") {
    if (isRefreshing) return;
    setRefreshError(null);
    setSyncDone(false);
    setIsRefreshing(true);
    setShowFullSync(false);
    try {
      await api.syncNow(scope);
      // Sync started in background — polling will detect when it finishes
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : "Nie udało się odświeżyć danych.");
      setIsRefreshing(false);
    }
  }

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-slate-900 text-white flex flex-col shadow-xl z-10">
      <div className="px-5 py-5 border-b border-slate-700">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-bold tracking-tight">BI Shoper</h1>
            <p className="text-xs text-slate-400 mt-0.5">Analityka sklepu</p>
          </div>
          <div className="relative">
            <div className="flex items-center">
              <button
                type="button"
                onClick={() => void handleRefresh("quick")}
                disabled={isRefreshing}
                className="inline-flex items-center gap-1 rounded-l-md border border-slate-600 px-2 py-1 text-[11px] font-medium text-slate-200 transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                title="Szybkie odświeżenie — tylko nowe zamówienia + transform (sekundy)"
              >
                {isRefreshing ? (
                  <>
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Sync...
                  </>
                ) : "Odśwież"}
              </button>
              <button
                type="button"
                onClick={() => setShowFullSync((v) => !v)}
                disabled={isRefreshing}
                className="inline-flex items-center rounded-r-md border border-l-0 border-slate-600 px-1 py-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200 disabled:opacity-60 disabled:cursor-not-allowed"
                title="Więcej opcji synchronizacji"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
            {showFullSync && !isRefreshing && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-slate-800 border border-slate-600 rounded-lg shadow-xl w-52 py-1 text-[11px]">
                <div className="px-3 py-1.5 text-slate-400 font-semibold uppercase tracking-wide text-[10px]">
                  Synchronizacja
                </div>
                <button
                  type="button"
                  onClick={() => void handleRefresh("quick")}
                  className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-700 transition-colors"
                >
                  <p className="font-medium">Szybka (zamówienia)</p>
                  <p className="text-slate-400 text-[10px] mt-0.5">Tylko nowe zamówienia + transform — sekundy</p>
                </button>
                <button
                  type="button"
                  onClick={() => void handleRefresh("all")}
                  className="w-full text-left px-3 py-2 text-slate-200 hover:bg-slate-700 transition-colors"
                >
                  <p className="font-medium">Pełna synchronizacja</p>
                  <p className="text-slate-400 text-[10px] mt-0.5">Wszystko od nowa — może trwać kilka minut</p>
                </button>
              </div>
            )}
          </div>
        </div>
        {refreshError ? (
          <p className="mt-2 text-[11px] text-rose-300">{refreshError}</p>
        ) : syncDone ? (
          <p className="mt-2 text-[11px] text-emerald-400">Synchronizacja zakończona ✓</p>
        ) : isRefreshing ? (
          <p className="mt-2 text-[11px] text-slate-400">Pobieranie nowych zamówień…</p>
        ) : null}
      </div>
      <nav className="flex-1 py-4 space-y-1 px-3">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d={n.icon} />
            </svg>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-slate-700 text-xs text-slate-500">
        MK-FOAM &middot; v0.1
      </div>
    </aside>
  );
}

export default function App() {
  usePageView();

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/products" element={<Products />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/retention" element={<Retention />} />
          <Route path="/traffic" element={<Traffic />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/price-update" element={<PriceUpdate />} />
          <Route path="/variant-codes" element={<VariantCodes />} />
        </Routes>
      </main>
    </div>
  );
}
