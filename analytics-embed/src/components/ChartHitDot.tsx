/** Klikalny punkt na linii: bez „pustych” kółek — widoczna kropka tylko dla wybranego dnia. */
export function LineHitDot(
  props: { cx?: number; cy?: number; payload?: { date?: string } },
  selectedDate: string | null,
  onToggle: (date: string) => void,
) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload?.date) return null;
  const on = selectedDate === payload.date;
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={16}
        fill="transparent"
        style={{ cursor: "pointer" }}
        onClick={(ev) => {
          ev.stopPropagation();
          onToggle(payload.date!);
        }}
      />
      {on ? <circle cx={cx} cy={cy} r={5} fill="#6366f1" /> : null}
    </g>
  );
}
