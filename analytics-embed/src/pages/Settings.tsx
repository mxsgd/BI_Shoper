import { useEffect, useState } from "react";
import { api } from "../api";

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

  useEffect(() => {
    api.getTrackingSettings()
      .then((s) => {
        setSavedMeasurementId(s.ga4_measurement_id);
        setMeasurementInput(s.ga4_measurement_id ?? "");
        setSavedPropertyId(s.ga4_property_id);
        setPropertyInput(s.ga4_property_id ?? "");
        setPropertyIsOverride(s.ga4_property_id_is_override);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const result = await api.updateTrackingSettings({
        ga4_measurement_id: measurementInput.trim() === "" ? null : measurementInput.trim(),
        ga4_property_id: propertyInput.trim() === "" ? null : propertyInput.trim(),
      });
      setSavedMeasurementId(result.ga4_measurement_id);
      setMeasurementInput(result.ga4_measurement_id ?? "");
      setSavedPropertyId(result.ga4_property_id);
      setPropertyInput(result.ga4_property_id ?? "");
      setPropertyIsOverride(result.ga4_property_id_is_override);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się zapisać ustawień.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loader />;

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
        {saved && <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-3 py-2">Zapisano. Odśwież stronę / kliknij „Odśwież” w menu, aby zmiany zaczęły działać.</p>}
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
