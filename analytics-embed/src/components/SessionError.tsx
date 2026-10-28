import { t } from "../i18n";
/** Shown instead of the panel when the signed Shoper session cannot be loaded. */
export default function SessionError({ noSession }: { noSession: boolean }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-700">
        <h1 className="mb-2 text-base font-semibold text-slate-900">
          {noSession ? t("Brak aktywnej sesji", "No active session") : t("Nie udało się połączyć z serwerem", "Could not reach the server")}
        </h1>
        <p>
          {noSession
            ? t("Otwórz aplikację z panelu administracyjnego Shoper. Jeśli sesja wygasła, odśwież stronę panelu.", "Open the app from the Shoper admin panel. If the session expired, reload the panel page.")
            : t("Spróbuj odświeżyć stronę za chwilę.", "Try reloading the page in a moment.")}
        </p>
      </div>
    </div>
  );
}
