interface PlanStageProps { diagnostic?: string; digest?: string; bytes?: unknown; canApprove: boolean; busy: boolean; onApprove(): void; onRun(): void; canRun: boolean; }
export function PlanStage({ diagnostic, digest, bytes, canApprove, busy, onApprove, onRun, canRun }: PlanStageProps) {
  return <section className="stage-panel" aria-labelledby="plan-heading"><h2 id="plan-heading">计划审批</h2>{diagnostic ? <><pre>{diagnostic}</pre><p>摘要：{digest ?? "未提供"}（{String(bytes ?? "未提供")} bytes）</p></> : <p>尚未收到可审阅计划，或计划内容不完整。</p>}{canApprove && <button type="button" disabled={busy} onClick={onApprove}>批准计划</button>}{canRun && <button type="button" disabled={busy} onClick={onRun}>继续运行</button>}</section>;
}
