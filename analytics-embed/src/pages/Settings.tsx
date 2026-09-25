import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Ga4ResyncStatus } from "../api";

export default function Settings() {
  const [measurementInput, setMeasurementInput] = useState("");
  const [propertyInput, setPropertyInput] = useState("");
  const [savedMeasurementId, setSavedMeasurementId] = useState<string | null>(null);
  const [savedPropertyId, setSavedPropertyId] = useState<string | null>(null);
  const [propertyIsOverride, setPropertyIsOverride] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [showResyncPrompt, setShowResyncPrompt] = useState(false);
  const [resyncDays, setResyncDays] = useState(90);
  const [resyncStatus, setResyncStatus] = useState<Ga4ResyncStatus | null>(null);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    Promise.all([api.getTrackingSettings(), api.getGa4ResyncStatus()])
      .then(([s, rs]) => {
        setSavedMeasurementId(s.ga4_measurement_id);
        setMeasurementInput(s.ga4_measurement_id ?? "");
        setSavedPropertyId(s.ga4_property_id);
        setPropertyInput(s.ga4_property_id ?? "");
        setPropertyIsOverride(s.ga4_property_id_is_override);
        setResyncStatus(rs);
        if (rs.status === "running") startPolling();
      })
      .finally(() => setLoading(false));
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startPolling() {
    stopPolling();
    pollTimer.current = window.setInterval(async () => {
      const rs = await api.getGa4ResyncStatus();
      setResyncStatus(rs);
      if (rs.status !== "running") stopPolling();
    }, 2000);
  }

  function stopPolling() {
    if (pollTimer.current !== null) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    const prevMeasurement = savedMeasurementId;
    const prevProperty = savedPropertyId;
    try {
      const nextMeasurement = measurementInput.trim() === "" ? null : measurementInput.trim();
      const nextProperty = propertyInput.trim() === "" ? null : propertyInput.trim();
      const result = await api.updateTrackingSettings({
        ga4_measurement_id: nextMeasurement,
        ga4_property_id: nextProperty,
      });
      setSavedMeasurementId(result.ga4_measurement_id);
      setMeasurementInput(result.ga4_measurement_id ?? "");
      setSavedPropertyId(result.ga4_property_id);
      setPropertyInput(result.ga4_property_id ?? "");
      setPropertyIsOverride(result.ga4_property_id_is_override);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);

      const changed = result.ga4_measurement_id !== prevMeasurement || result.ga4_property_id !== prevProperty;
      if (changed) setShowResyncPrompt(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się zapisać ustawień.");
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmResync() {
    setShowResyncPrompt(false);
    await api.resyncGa4(resyncDays);
    const rs = await api.getGa4ResyncStatus();
    setResyncStatus(rs);
    startPolling();
  }

  if (loading) return <Loader />;

  const resyncRunning = resyncStatus?.status === "running";

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-1">Ustawienia</h2>
      <p className="text-sm text-slate-500 mb-6">Konfiguracja panelu BI</p>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">Google tag panelu (gtag.js)</h3>
        <p className="text-xs text-slate-500 mb-4">
          Identyfikator pomiaru GA4 (np. <code className="font-mono">G-XXXXXXXXXX</code>), którym śledzony
          jest ten panel BI. To osobny tag od tego, który powinien być zainstalowany na sklepie —
          jeśli oba wskazują tę samą usługę GA4, wizyty w panelu zniekształcają dane ruchu ze sklepu
          w zakładce „Ruch”. Zostaw puste, aby wyłączyć śledzenie panelu.
        </p>

        <label className="block text-xs font-medium text-slate-600 mb-1.5">Measurement ID</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={measurementInput}
            onChange={(e) => setMeasurementInput(e.target.value)}
            placeholder="G-XXXXXXXXXX"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            type="button"
            onClick={() => setMeasurementInput("")}
            disabled={saving || !measurementInput}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors"
          >
            Wyczyść
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Aktualnie zapisany tag: {savedMeasurementId ? <span className="font-mono text-slate-600">{savedMeasurementId}</span> : <span className="italic">brak (śledzenie panelu wyłączone)</span>}
        </p>
      </div>

      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 mb-1">Właściwość GA4 do raportów (Ruch)</h3>
        <p className="text-xs text-slate-500 mb-4">
          Numeryczne ID właściwości Google Analytics 4 (np. <code className="font-mono">530034470</code>),
          z której backend pobiera dane sesji/ruchu do zakładki „Ruch”. Nadpisuje wartość{" "}
          <code className="font-mono">GA4_PROPERTY_ID</code> z <code className="font-mono">backend/.env</code>.
          Zostaw puste, aby wrócić do wartości z <code className="font-mono">.env</code>.
        </p>

        <label className="block text-xs font-medium text-slate-600 mb-1.5">Property ID</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={propertyInput}
            onChange={(e) => setPropertyInput(e.target.value)}
            placeholder="530034470"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <button
            type="button"
            onClick={() => setPropertyInput("")}
            disabled={saving || !propertyInput}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors"
          >
            Wyczyść
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Aktualnie używana właściwość: {savedPropertyId ? <span className="font-mono text-slate-600">{savedPropertyId}</span> : <span className="italic">brak</span>}
          {savedPropertyId && (
            <span className="text-slate-400"> ({propertyIsOverride ? "nadpisana tutaj" : "z .env"})</span>
          )}
        </p>

        {resyncStatus && resyncStatus.status !== "idle" && (
          <div className={`mt-4 rounded-lg px-3 py-2 text-xs border ${
            resyncRunning
              ? "bg-indigo-50 border-indigo-100 text-indigo-700"
              : resyncStatus.status === "error"
              ? "bg-rose-50 border-rose-100 text-rose-700"
              : "bg-emerald-50 border-emerald-100 text-emerald-700"
          }`}>
            {resyncRunning && "Przeładowywanie danych GA4 w toku… to może potrwać kilka minut."}
            {resyncStatus.status === "done" && "Przeładowanie danych GA4 zakończone. Odśwież zakładkę „Ruch”, aby zobaczyć nowe dane."}
            {resyncStatus.status === "error" && `Błąd przeładowania: ${resyncStatus.error}`}
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowResyncPrompt(true)}
          disabled={resyncRunning || !savedPropertyId}
          className="mt-4 text-xs font-medium text-indigo-600 hover:text-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Przeładuj historyczne dane GA4 ręcznie →
        </button>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? "Zapisywanie..." : "Zapisz zmiany"}
        </button>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded px-3 py-2">{error}</p>}
        {saved && <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-3 py-2">Zapisano.</p>}
      </div>

      {showResyncPrompt && (
        <ResyncModal
          days={resyncDays}
          onDaysChange={setResyncDays}
          onConfirm={() => void handleConfirmResync()}
          onCancel={() => setShowResyncPrompt(false)}
        />
      )}
    </div>
  );
}

function ResyncModal({
  days,
  onDaysChange,
  onConfirm,
  onCancel,
}: {
  days: number;
  onDaysChange: (v: number) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <h3 className="text-lg font-bold mb-2">Przeładować dane GA4 wstecz?</h3>
        <p className="text-sm text-slate-600 mb-4">
          Zmieniłeś tag i/lub właściwość GA4. Stare dane w zakładce „Ruch” pochodzą z poprzedniej
          konfiguracji i mogą nie zgadzać się z nową. Czy usunąć dotychczasowe dane GA4 i pobrać je
          ponownie wstecz z nowej właściwości?
        </p>

        <label className="block text-xs font-medium text-slate-600 mb-1.5">Ile dni wstecz</label>
        <input
          type="number"
          min={1}
          max={365}
          value={days}
          onChange={(e) => onDaysChange(Math.min(365, Math.max(1, Number(e.target.value) || 1)))}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm mb-5 focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Nie, zostaw stare dane
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            Tak, przeładuj dane
          </button>
        </div>
      </div>
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
