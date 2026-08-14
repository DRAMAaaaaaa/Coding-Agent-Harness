import { FormEvent } from "react";
import type { Workspace } from "../../types";

interface ProjectStageProps { path: string; workspace?: Workspace; busy: boolean; mutationDisabled: boolean; onPath(value: string): void; onConnect(): void; onTrust(): void; }
export function ProjectStage({ path, workspace, busy, mutationDisabled, onPath, onConnect, onTrust }: ProjectStageProps) {
  const submit = (event: FormEvent): void => { event.preventDefault(); onConnect(); };
  return <section className="stage-panel" aria-labelledby="project-heading"><h2 id="project-heading">项目接入</h2><p>先识别本地仓库，再显式建立信任。</p><form onSubmit={submit}><label htmlFor="project-path">项目路径</label><div className="inline-form"><input id="project-path" value={path} onChange={(event) => onPath(event.target.value)} required /><button type="submit" disabled={busy}>接入项目</button></div></form>
    {workspace && <div className="summary"><p>{workspace.languages.join(", ") || "未识别语言"} · {workspace.default_branch}</p><p>已跟踪 {workspace.repository?.tracked_count ?? 0} 项，测试 {workspace.repository?.test_count ?? 0} 项，未提交变更 {workspace.repository?.dirty_count ?? 0} 项。</p>{workspace.repository?.test_paths?.length ? <p>测试位置：{workspace.repository.test_paths.join(", ")}</p> : null}{!workspace.trusted ? <button type="button" disabled={mutationDisabled} onClick={onTrust}>建立信任</button> : <p>✓ 当前项目已建立信任</p>}</div>}
  </section>;
}
