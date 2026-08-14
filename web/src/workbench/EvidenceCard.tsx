import type { ReactNode } from "react";

interface EvidenceCardProps { title: string; children: ReactNode; tone?: "neutral" | "success" | "warning"; }
export function EvidenceCard({ title, children, tone = "neutral" }: EvidenceCardProps) {
  return <article className={`evidence-card evidence-${tone}`}><h3>{title}</h3>{children}</article>;
}
