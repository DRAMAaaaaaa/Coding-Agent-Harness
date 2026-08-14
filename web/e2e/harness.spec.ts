import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { terminateAndWait } from "./processControl";

interface ReadyInfo {
  url: string;
  fixture: string;
  initial_head: string;
  worktree_root: string;
}

const repoRoot = path.resolve(import.meta.dirname, "../..");
const python = process.platform === "win32"
  ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
  : path.join(repoRoot, ".venv", "bin", "python");

async function waitForReady(file: string, process: ChildProcess): Promise<ReadyInfo> {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) throw new Error(`demo service exited: ${process.exitCode}`);
    try { return JSON.parse(await readFile(file, "utf8")) as ReadyInfo; } catch { await new Promise((resolve) => setTimeout(resolve, 50)); }
  }
  throw new Error("demo service readiness timeout");
}

function isolatedGitEnvironment(home: string): Record<string, string> {
  const environment: Record<string, string> = {
    HOME: home,
    USERPROFILE: home,
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_TERMINAL_PROMPT: "0",
  };
  for (const key of ["PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"]) {
    const value = process.env[key];
    if (value) environment[key] = value;
  }
  return environment;
}

async function runIsolatedGit(root: string, home: string, ...arguments_: string[]): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const git = spawn("git", ["-C", root, ...arguments_], { env: isolatedGitEnvironment(home) });
    let output = "";
    git.stdout.on("data", (chunk) => { output += String(chunk); });
    git.once("exit", (code) => code === 0 ? resolve(output.trim()) : reject(new Error(`git exit ${code}`)));
  });
}

test("真实浏览器完成受治理的 Harness 主路径并回收工作树", async ({ page }) => {
  const scratch = await mkdtemp(path.join(tmpdir(), "harness-e2e-"));
  const readyFile = path.join(scratch, "ready.json");
  const runtimeRoot = path.join(scratch, "runtime");
  const poisonConfig = path.join(scratch, ".gitconfig");
  await writeFile(poisonConfig, "[malformed\n", "utf8");
  const previousHome = process.env.HOME;
  const previousUserProfile = process.env.USERPROFILE;
  process.env.HOME = scratch;
  process.env.USERPROFILE = scratch;
  const isolatedGitHome = path.join(scratch, "isolated-git-home");
  await mkdir(isolatedGitHome);
  const child = spawn(python, [
    "scripts/serve_demo.py", "--ready-file", readyFile, "--runtime-root", runtimeRoot,
    "--keep-alive",
  ], {
    cwd: repoRoot,
    detached: process.platform !== "win32",
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONPATH: path.join(repoRoot, "src") },
  });
  child.stdout?.resume();
  child.stderr?.resume();
  try {
    const ready = await waitForReady(readyFile, child);
    await page.goto(ready.url);
    await page.getByLabel("项目路径").fill(ready.fixture);
    await page.getByRole("button", { name: "接入项目" }).click();
    await expect(page.getByText(/已跟踪/)).toBeVisible();
    await page.getByRole("button", { name: "建立信任" }).click();
    await page.getByLabel("编码需求").fill("把 VALUE 从 1 修改为 2，并运行测试");
    await page.getByRole("button", { name: "生成计划" }).click();
    await expect(page.getByText("先验证失败，再修改并重新验证，最后展示差异。", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "批准计划" }).click();
    await expect(page.getByText("等待用户处理", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "回放与纠正" }).click();
    await expect(page.getByRole("heading", { name: "回放与纠正" })).toBeVisible();
    await page.getByLabel("失败原因提问").fill("为什么失败？");
    await page.getByRole("button", { name: "提问" }).click();
    await expect(page.getByText("VALUE 仍为 1，因此验证失败。", { exact: true })).toBeVisible();
    await page.getByLabel("纠正说明").fill("将 VALUE 改为 2 后重新验证");
    const correctionResponse = page.waitForResponse((response) => response.url().includes("/correction-branches") && response.request().method() === "POST");
    await page.getByRole("button", { name: "从此纠正" }).click();
    const response = await correctionResponse;
    expect(response.status(), await response.text()).toBe(201);
    const correctionBranch = await response.json() as { id: string };
    await page.getByRole("button", { name: "计划审批" }).click();
    await page.getByRole("button", { name: "批准计划" }).click();
    await page.getByRole("button", { name: "回放与纠正" }).click();
    await expect(page.getByLabel("纠正分支比较")).toBeVisible();
    await expect(page.getByText(/子任务：/)).toBeVisible();
    await page.getByRole("button", { name: "交付与经验" }).click();
    await expect(page.getByText("测试已通过", { exact: true })).toBeVisible();
    await expect(page.getByText(/-VALUE = 1/).last()).toBeVisible();
    await expect(page.getByText(/\+VALUE = 2/).last()).toBeVisible();
    await page.getByRole("button", { name: "批准最终审查" }).click();
    await expect(page.getByText(/已完成/)).toBeVisible();
    const finalComparison = await page.request.get(`${ready.url}/api/correction-branches/${correctionBranch.id}/comparison`);
    expect(finalComparison.ok(), await finalComparison.text()).toBeTruthy();
    const comparison = await finalComparison.json() as { child_state: string; child_diff: string | null };
    expect(comparison.child_state).toBe("COMPLETED");
    expect(comparison.child_diff).toContain("+VALUE = 2");
    await page.getByLabel("项目经验").fill("先运行聚焦测试再修改");
    await page.getByRole("button", { name: "批准经验" }).click();
    await page.getByRole("button", { name: "需求描述" }).click();
    await expect(page.getByLabel("下一任务项目经验")).toContainText("先运行聚焦测试再修改");
    await page.getByLabel("编码需求").fill("应用已批准的项目经验");
    const nextTaskResponse = page.waitForResponse((next) => next.url().endsWith("/api/tasks") && next.request().method() === "POST");
    await page.getByRole("button", { name: "生成计划" }).click();
    const nextTask = await (await nextTaskResponse).json() as { id: string };
    await page.getByRole("button", { name: "需求描述" }).click();
    await expect(page.getByText(/经验 ID：/)).toBeVisible();
    await page.getByRole("button", { name: "计划审批" }).click();
    await expect(page.getByText("已应用项目经验，先运行验证。", { exact: true })).toBeVisible();
    const firstActionPromise = page.evaluate(async (taskId) => await new Promise<{ tool: string }>((resolve, reject) => {
      const source = new EventSource(`/api/tasks/${taskId}/events?after=0`);
      source.addEventListener("task-event", (message) => { const event = JSON.parse((message as MessageEvent<string>).data) as { event_type: string; payload: { action?: { tool?: string } } }; if (event.event_type === "ACTION_PARSED") { source.close(); resolve({ tool: event.payload.action?.tool ?? "" }); } });
      source.onerror = () => { source.close(); reject(new Error("SSE failed before ACTION_PARSED")); };
    }), nextTask.id);
    await page.getByRole("button", { name: "批准计划" }).click();
    const firstAction = await firstActionPromise;
    expect(firstAction.tool).toBe("run_verification");
    await page.close();
    const head = await runIsolatedGit(ready.fixture, isolatedGitHome, "rev-parse", "HEAD");
    expect(head).toBe(ready.initial_head);
    const status = await runIsolatedGit(ready.fixture, isolatedGitHome, "status", "--porcelain=v1");
    expect(status).toBe("");
  } finally {
    if (previousHome === undefined) delete process.env.HOME;
    else process.env.HOME = previousHome;
    if (previousUserProfile === undefined) delete process.env.USERPROFILE;
    else process.env.USERPROFILE = previousUserProfile;
    child.stdin?.end();
    await terminateAndWait(child);
    await rm(scratch, { recursive: true, force: true });
  }
});
