import type { TaskEvent } from "../../types";
import { EvidenceCard } from "../EvidenceCard";
import { TechnicalDetails } from "../TechnicalDetails";
interface ExecutionStageProps { events: readonly TaskEvent[]; verification?: string; approvals: ReadonlyArray<{ reason: string; scope: string }>; reconnecting: boolean; finalReviewBlocked: boolean; }
export function ExecutionStage({ events, verification, approvals, reconnecting, finalReviewBlocked }: ExecutionStageProps) {
  return <section className="stage-panel" aria-labelledby="execution-heading"><h2 id="execution-heading">执行与验证</h2><div className="evidence-grid"><EvidenceCard title="最近验证" tone={verification ? "success" : "neutral"}><p>{verification ? `测试已通过：${verification}` : "等待测试结果"}</p></EvidenceCard><EvidenceCard title="治理护栏" tone={approvals.length ? "warning" : "neutral"}>{approvals.length ? approvals.map((item) => <p key={`${item.reason}:${item.scope}`}>原因：{item.reason}；范围：{item.scope}</p>) : <p>当前没有待审批危险动作。后端尚无可提交操作。</p>}</EvidenceCard></div>{finalReviewBlocked && <p>终审证据不完整，需等待当前轮次的完整差异、最终摘要和验证结果。</p>}{reconnecting && <p>事件流断开，正在重连；变更操作已禁用。</p>}<TechnicalDetails events={events} /></section>;
}
