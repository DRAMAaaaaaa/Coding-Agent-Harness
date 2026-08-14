import { FormEvent } from "react";
import type { ProjectLearningCard } from "../../types";

interface RequirementStageProps { requirement: string; trusted: boolean; mutationDisabled: boolean; busy: boolean; projectLearning?: ProjectLearningCard; providerLabel: string; onRequirement(value: string): void; onCreate(): void; }
export function RequirementStage({ requirement, trusted, mutationDisabled, busy, projectLearning, providerLabel, onRequirement, onCreate }: RequirementStageProps) {
  const submit = (event: FormEvent): void => { event.preventDefault(); onCreate(); };
  return <section className="stage-panel" aria-labelledby="requirement-heading"><h2 id="requirement-heading">需求描述</h2><p>{providerLabel}</p>{projectLearning && <aside aria-label="下一任务项目经验"><p>经验 ID：{projectLearning.id}</p><p>{projectLearning.text}</p></aside>}<form onSubmit={submit}><label htmlFor="requirement">编码需求</label><textarea id="requirement" value={requirement} onChange={(event) => onRequirement(event.target.value)} required /><button type="submit" disabled={!trusted || mutationDisabled}>{busy ? "正在生成" : "生成计划"}</button></form></section>;
}
