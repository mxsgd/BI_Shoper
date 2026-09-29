/** Shown instead of the panel when the signed Shoper session cannot be loaded. */
export default function SessionError({ noSession }: { noSession: boolean }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-700">
        <h1 className="mb-2 text-base font-semibold text-slate-900">
          {noSession ? "Brak aktywnej sesji" : "Nie udało się połączyć z serwerem"}
        </h1>
        <p>
          {noSession
            ? "Otwórz aplikację z panelu administracyjnego Shoper. Jeśli sesja wygasła, odśwież stronę panelu."
            : "Spróbuj odświeżyć stronę za chwilę."}
        </p>
      </div>
    </div>
  );
}
