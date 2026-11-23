import { dateTime, label, STATUS_TEXT } from "@/lib/format";
import type { HistoryItem } from "@/lib/types";

export function Timeline({ items, showNotes = false }: { items: HistoryItem[]; showNotes?: boolean }) {
  return (
    <ol className="relative ml-2 border-l border-border-strong">
      {items.map((h, i) => (
        <li key={i} className="mb-5 ml-5">
          <span className="absolute -left-[7px] mt-1 h-3 w-3 rounded-full border-2 border-surface bg-primary" aria-hidden />
          <p className="text-sm font-medium">{STATUS_TEXT[h.to_status] ?? label(h.to_status)}</p>
          <p className="text-xs text-text-muted">{dateTime(h.created_at)} · by {h.actor_type}</p>
          {showNotes && h.note && <p className="mt-1 text-sm text-text-muted">{h.note}</p>}
        </li>
      ))}
    </ol>
  );
}
