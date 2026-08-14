# 五分钟演示：共学回放工作台

本演示只使用仓库内 `examples/python_demo` 与 `ScriptedMockProvider`；不访问网络、不填写 API Key、不把真实项目或凭据带入课堂。

## 准备（约 30 秒）

```powershell
npm.cmd --prefix web run build
.venv\Scripts\python.exe scripts\serve_demo.py --ready-file .tmp\ready.json --max-seconds 600
```

从 `.tmp\ready.json` 读取 ready JSON 中的 localhost URL。请从 `.tmp\ready.json` 复制 `fixture` 字段值到“项目路径”，再输入需求“把 VALUE 修改为 2 并通过测试”。若改用自动验收，执行 `make test-e2e`；它会启动临时 Git fixture 和本地服务。

## 六阶段工作台主路径（约 3 分钟）

1. **项目接入**：填写“项目路径”，点击“接入项目”，审阅摘要后点击“建立信任”，确认只接入本地示例。
2. **需求描述**：输入编码需求；此处可查看“下一任务项目经验”（如有），点击“生成计划”。
3. **计划审批**：阅读完整计划与摘要，点击“批准计划”。
4. **执行与验证**：查看“最近验证”“治理护栏”和技术详情；等待当前验证证据出现。
5. **回放与纠正**：选择失败意图卡，在“失败原因提问”输入问题并点击“提问”；需要修订时填写纠正说明并点击“从此纠正”。子任务切换后再次进入“计划审批”，等到其计划完整出现再点击“批准计划”，随后回看“纠正分支比较”。
6. **交付与经验**：确认当前轮次的测试、最终差异、最终摘要完整后点击“批准最终审查”；填写“项目经验”并点击“批准经验”，下一任务可见该经验。

不要替用户点击任何危险操作的审批，也不要把 UI 中的 Provider 配置当作已完成真实连接。失败提问是只读、零工具操作；纠正分支只从失败节点开始。

## 三项确定性机制（约 1 分钟）

```powershell
make demo
```

预期仅输出：

```text
PASS governance_guard
PASS feedback_changed_action
PASS deterministic_stop
```

分别说明危险删除被代码治理层零调用拦截、注入验证失败会改变下一动作、相同失败指纹无进展时停止并等待人工。`scripts/mechanism_demo.py` 使用 Scripted Mock，不访问网络。

## 结束检查（约 30 秒）

- 任务只在临时 worktree 修改；原 fixture 的 HEAD/工作区保持不受污染。
- 仅将已完成任务的最终交付批准为项目经验；不要记录秘密或个人数据。
- 服务完成最终批准或超时后退出；保留必要的本地证据，不虚报真实 Provider、Docker daemon、Nginx 或 ECS 浏览器验收。
