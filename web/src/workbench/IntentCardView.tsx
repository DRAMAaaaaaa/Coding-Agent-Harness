import { FormEvent } from "react";
import type { IntentCard } from "../types";

interface IntentCardViewProps {
  card: IntentCard; question: string; answer: string; correction: string; busy: boolean; branchExists: boolean;
  onQuestion(value: string): void; onAsk(): void; onCorrection(value: string): void; onCreateCorrection(): void;
}
export function IntentCardView({ card, question, answer, correction, busy, branchExists, onQuestion, onAsk, onCorrection, onCreateCorrection }: IntentCardViewProps) {
  const submit = (event: FormEvent, callback: () => void): void => { event.preventDefault(); callback(); };
  return <article className="intent-card"><h3>{card.intent}</h3><p>{card.actual_result}</p>
    {card.kind === "verification_failure" && <form onSubmit={(event) => submit(event, onAsk)}><label htmlFor={`failure-question-${card.id}`}>失败原因提问</label><input id={`failure-question-${card.id}`} value={question} maxLength={4096} onChange={(event) => onQuestion(event.target.value)} required /><button type="submit" disabled={busy}>提问</button>{answer && <p>{answer}</p>}</form>}
    {card.kind === "verification_failure" && !branchExists && <form onSubmit={(event) => submit(event, onCreateCorrection)}><label htmlFor={`correction-${card.id}`}>纠正说明</label><input id={`correction-${card.id}`} value={correction} maxLength={8192} onChange={(event) => onCorrection(event.target.value)} required /><button type="submit" disabled={busy}>从此纠正</button></form>}
  </article>;
}
