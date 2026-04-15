export function FocusBanner({
  selectedDate,
  onClear,
  subtitle,
}: {
  selectedDate: string | null;
  onClear: () => void;
  subtitle?: string;
}) {
  if (!selectedDate) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm text-indigo-950">
      <p>
        <span className="text-indigo-700">Widok zawężony do dnia </span>
        <strong className="font-semibold tabular-nums">{selectedDate}</strong>
        {subtitle ? <span className="text-indigo-700"> — {subtitle}</span> : null}
      </p>
      <button
        type="button"
        onClick={onClear}
        className="shrink-0 rounded-md bg-white px-3 py-1 text-xs font-medium text-indigo-800 shadow-sm ring-1 ring-indigo-200 hover:bg-indigo-100"
      >
        Pokaż cały okres
      </button>
    </div>
  );
}
