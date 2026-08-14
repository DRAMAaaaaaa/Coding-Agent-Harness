# 课程反思写作提纲（学生本人完成）

**篇幅：1500–2500 字。必须由学生本人撰写。** 本文件只提供问题、可核对的证据路径和建议字数，不提供可提交的第一人称答案。AI 仅可辅助整理或润色；如使用，须在提交处标注辅助范围、提示内容概要和本人复核方式。

写作前：用自己的经历回答，区分亲自执行、观察到的仓库证据与尚未完成的验收；不要虚构个人判断、真实 Provider 调用或 Docker/Nginx/ECS 结果。

## Superpowers 技能

建议 180–250 字：选择哪些技能改变了决策顺序？它们如何约束了 brainstorming、计划、隔离和审查？证据路径：`AGENTS.md`、`SPEC_PROCESS.md`、`PLAN.md` 的 2026-08-14 联合计划记录。

## TDD

建议 180–250 字：挑一个亲自经历的 RED→GREEN→重构循环，RED 为何能证明契约缺失？哪些后续验证支持或限制结论？证据路径：`tests/distribution/test_delivery_files.py`、`AGENT_LOG.md`、`.superpowers/sdd/task-5-report.md`。

## subagent-driven

建议 150–220 字：独立任务/审查的分工如何帮助或妨碍理解？哪些信息必须由主控复核，而不能仅相信报告？证据路径：`SPEC_PROCESS.md` 的冷启动与工作台记录、`PLAN.md` 的双重审查要求。

## SPEC / PLAN

建议 180–250 字：规格、精确计划和最终变更之间是否有冲突？如何处理历史 Task 5 与本轮共学工作台 Task 5 同名的导航问题？证据路径：`SPEC.md`、`PLAN.md`、`docs/archive/plans/2026-08-14-co-learning-workbench-and-docs.md`。

## Prompt / Context

建议 180–250 字：有限上下文、证据定位和不确定项如何影响实现/审查？哪些话不能写成已验收？证据路径：`docs/FEATURES.md`、`README.md`、`docs/DEPLOYMENT.md`。

## 凭据与分发

建议 180–250 字：如何避免把凭据写入日志、测试、文档和演示？本地 Mock、Docker 与短时公网边界分别是什么？证据路径：`docs/SECURITY.md`、`.env.example`、`docs/DEPLOYMENT.md`、`scripts/secret_scan.py`。

## 方法论批判

建议 200–300 字：该流程的成本、盲区或不适用场景是什么？确定性 Mock、人工批准、隔离 worktree 和长过程文档各有什么局限？用具体仓库事实支持，而非泛泛评价。证据路径：`docs/archive/ledgers/DEFERRED_WORK.md`、`docs/FEATURES.md`、测试输出记录。

## 如果重做

建议 180–250 字：基于亲身过程，会保留、删减或改造哪一步？如何把改进转成可测试、可验收的计划，而非愿望？证据路径：`PLAN.md` 的未验收项、`AGENT_LOG.md` 的事实时间线。

提交前自查：总字数在范围内；所有第一人称判断确属本人；AI 辅助已标注；许可表中“待学生复核”已处理；未把未执行的动态验收写成通过。
