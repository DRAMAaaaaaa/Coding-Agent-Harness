import { STAGES, type WorkbenchStage } from "./workflow";

interface StageNavigatorProps {
  selected: WorkbenchStage;
  latest: WorkbenchStage;
  unlocked: readonly WorkbenchStage[];
  onSelect(stage: WorkbenchStage): void;
}

export function StageNavigator({ selected, latest, unlocked, onSelect }: StageNavigatorProps) {
  const labels: Record<WorkbenchStage, string> = {
    PROJECT: "项目接入", REQUIREMENT: "需求描述", PLAN: "计划审批", EXECUTION: "执行与验证", REPLAY: "回放与纠正", DELIVERY: "交付与经验",
  };
  return <nav className="stage-nav" aria-label="任务阶段">
    {STAGES.map((stage, index) => {
      const available = unlocked.includes(stage.id);
      return <button
        key={stage.id}
        type="button"
        className="stage-button"
        disabled={!available}
        aria-label={labels[stage.id]}
        aria-current={selected === stage.id ? "step" : undefined}
        onClick={() => onSelect(stage.id)}
      >{index + 1}. {stage.label}</button>;
    })}
    {selected !== latest && <button type="button" className="back-to-current" onClick={() => onSelect(latest)}>返回当前阶段</button>}
  </nav>;
}
