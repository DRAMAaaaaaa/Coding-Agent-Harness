import type { ReactNode } from "react";
import type { TaskEvent } from "../types";

interface TechnicalDetailsProps { events: readonly TaskEvent[]; children?: ReactNode; }

export function TechnicalDetails({ events, children }: TechnicalDetailsProps) {
  return <details className="technical-details">
    <summary>技术详情</summary>
    {children}
    <p aria-live="polite">{events.at(-1) ? `新事件 #${events.at(-1)?.sequence} ${events.at(-1)?.event_type}` : "事件按序号续传。"}</p>
    <ol>{events.map((event) => <li key={event.sequence}><strong>#{event.sequence} {event.event_type}</strong></li>)}</ol>
  </details>;
}
