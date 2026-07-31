import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
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
  ], {
    cwd: repoRoot,
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
    await expect(page.getByText("测试已通过", { exact: true })).toBeVisible();
    await expect(page.getByText(/-VALUE = 1/)).toBeVisible();
    await expect(page.getByText(/\+VALUE = 2/)).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "FEEDBACK_RECORDED" })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "VERIFICATION_SUCCEEDED" })).toBeVisible();
    await page.getByRole("button", { name: "批准最终审查" }).click();
    await expect(page.getByText(/已完成/)).toBeVisible();
    await page.close();

    if (child.exitCode === null) await new Promise<void>((resolve, reject) => {
      child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`demo service exit ${code}`)));
    });
    expect(child.exitCode).toBe(0);
    const head = await runIsolatedGit(ready.fixture, isolatedGitHome, "rev-parse", "HEAD");
    expect(head).toBe(ready.initial_head);
    const status = await runIsolatedGit(ready.fixture, isolatedGitHome, "status", "--porcelain=v1");
    expect(status).toBe("");
    await expect(stat(ready.worktree_root)).rejects.toThrow();
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
