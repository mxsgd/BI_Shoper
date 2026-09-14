import { useEffect } from "react";
import { api } from "./api";

let loadedForId: string | null = null;

function loadGtagScript(measurementId: string) {
  if (loadedForId === measurementId) return;
  loadedForId = measurementId;
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  document.head.appendChild(script);
  window.gtag("config", measurementId, { send_page_view: false });
}

/** Loads gtag.js using the measurement ID configured in Ustawienia (falls back to no-op if unset). */
export function useGtagConfig() {
  useEffect(() => {
    let disposed = false;
    api.getTrackingSettings()
      .then((s) => {
        if (disposed || !s.ga4_measurement_id) return;
        loadGtagScript(s.ga4_measurement_id);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);
}
