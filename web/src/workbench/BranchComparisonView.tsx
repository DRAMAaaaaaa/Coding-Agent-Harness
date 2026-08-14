import type { BranchComparison } from "../types";

interface BranchComparisonViewProps { comparison: BranchComparison; }
export function BranchComparisonView({ comparison }: BranchComparisonViewProps) {
  return <article className="comparison-grid" aria-label="纠正分支比较">
    <section><h3>父任务</h3><p>父任务：{comparison.parent_state} — {comparison.parent_verification ?? "无验证摘要"}</p><pre>{comparison.parent_diff}</pre></section>
    <section><h3>子任务</h3><p>子任务：{comparison.child_state ?? "尚未创建"} — {comparison.child_verification ?? "无验证摘要"}</p><pre>{comparison.child_diff ?? "尚无子任务差异"}</pre></section>
  </article>;
}
