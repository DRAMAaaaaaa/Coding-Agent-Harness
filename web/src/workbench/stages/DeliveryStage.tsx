import { FormEvent } from "react";
import type { IntentCard } from "../../types";
interface DeliveryStageProps { verification?: string; diff?: string; summary?: string; canApprove: boolean; busy: boolean; taskCompleted: boolean; cards: readonly IntentCard[]; learningText: string; onApprove(): void; onLearning(value: string): void; onApproveLearning(card: IntentCard): void; }
export function DeliveryStage({ verification, diff, summary, canApprove, busy, taskCompleted, cards, learningText, onApprove, onLearning, onApproveLearning }: DeliveryStageProps) {
  const finalCard = cards.find((card) => card.kind === "final_delivery" && !card.learning_card_id);
  const submit = (event: FormEvent): void => { event.preventDefault(); if (finalCard) onApproveLearning(finalCard); };
  return <section className="stage-panel" aria-labelledby="delivery-heading"><h2 id="delivery-heading">交付与经验</h2><p>{verification ? <>✓ <span>测试已通过</span>：<span>{verification}</span></> : "○ 等待测试结果"}</p>{canApprove && <button type="button" disabled={busy} onClick={onApprove}>批准最终审查</button>}<h3>最终差异</h3><pre>{diff ?? "尚无差异摘要。"}</pre><h3>最终摘要</h3><pre>{summary ?? "尚无最终摘要。"}</pre>{taskCompleted && finalCard && <form onSubmit={submit}><label htmlFor="project-learning">项目经验</label><textarea id="project-learning" value={learningText} maxLength={2048} onChange={(event) => onLearning(event.target.value)} required /><button type="submit" disabled={busy}>批准经验</button></form>}</section>;
}
