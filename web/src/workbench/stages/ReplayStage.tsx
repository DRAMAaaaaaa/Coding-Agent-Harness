import type { BranchComparison, IntentCard } from "../../types";
import { BranchComparisonView } from "../BranchComparisonView";
import { IntentCardView } from "../IntentCardView";
interface ReplayStageProps { cards: readonly IntentCard[]; comparison?: BranchComparison; question: string; answer: string; correction: string; busy: boolean; onQuestion(value: string): void; onAsk(card: IntentCard): void; onCorrection(value: string): void; onCreateCorrection(card: IntentCard): void; }
export function ReplayStage({ cards, comparison, question, answer, correction, busy, onQuestion, onAsk, onCorrection, onCreateCorrection }: ReplayStageProps) {
  return <section className="stage-panel" aria-labelledby="replay-heading"><h2 id="replay-heading">回放与纠正</h2>{cards.length ? cards.map((card) => <IntentCardView key={card.id} card={card} question={question} answer={answer} correction={correction} busy={busy} branchExists={comparison !== undefined} onQuestion={onQuestion} onAsk={() => onAsk(card)} onCorrection={onCorrection} onCreateCorrection={() => onCreateCorrection(card)} />) : <p>等待意图、失败或治理证据后即可回放。</p>}{comparison && <BranchComparisonView comparison={comparison} />}</section>;
}
