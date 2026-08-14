import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";

import { terminateAndWait } from "./processControl";

test("协作关闭期内退出时不调用 Windows 进程树终止", async () => {
  const processEvents = new EventEmitter();
  const treeCalls: boolean[] = [];
  const child = Object.assign(processEvents, {
    exitCode: null as number | null,
    signalCode: null as NodeJS.Signals | null,
    pid: 21,
    kill(): boolean { return true; },
  });
  queueMicrotask(() => {
    child.exitCode = 0;
    child.emit("exit", 0, null);
  });

  await terminateAndWait(child, {
    cooperativeTimeoutMs: 50,
    platform: "win32",
    windowsTreeTerminator: async (_pid, force) => { treeCalls.push(force); },
  });

  expect(treeCalls).toEqual([]);
  expect(child.exitCode).toBe(0);
});

test("子进程忽略优雅退出时会强制终止并等待退出", async () => {
  const processEvents = new EventEmitter();
  const directSignals: Array<NodeJS.Signals | number | undefined> = [];
  const groupSignals: NodeJS.Signals[] = [];
  let groupAlive = true;
  const child = Object.assign(processEvents, {
    exitCode: null as number | null,
    signalCode: null as NodeJS.Signals | null,
    pid: 42,
    kill(signal?: NodeJS.Signals | number): boolean {
      directSignals.push(signal);
      return true;
    },
  });

  await terminateAndWait(child, {
    gracefulTimeoutMs: 1,
    forceTimeoutMs: 50,
    platform: "linux",
    posixGroupSignaler: (_processGroupId, signal) => {
      groupSignals.push(signal);
      if (signal === "SIGTERM") {
        child.signalCode = "SIGTERM";
        child.emit("exit", null, "SIGTERM");
      } else {
        groupAlive = false;
        child.signalCode = "SIGKILL";
      }
    },
    posixGroupExists: () => groupAlive,
  });

  expect(directSignals).toEqual([]);
  expect(groupSignals).toEqual(["SIGTERM", "SIGKILL"]);
  expect(child.signalCode).toBe("SIGKILL");
});

test("Windows 从首次终止起就回收进程树并等待父进程退出", async () => {
  const processEvents = new EventEmitter();
  const directSignals: Array<NodeJS.Signals | number | undefined> = [];
  const treeCalls: boolean[] = [];
  const child = Object.assign(processEvents, {
    exitCode: null as number | null,
    signalCode: null as NodeJS.Signals | null,
    pid: 84,
    kill(signal?: NodeJS.Signals | number): boolean {
      directSignals.push(signal);
      return true;
    },
  });

  await terminateAndWait(child, {
    gracefulTimeoutMs: 1,
    forceTimeoutMs: 50,
    platform: "win32",
    windowsTreeTerminator: async (_pid, force) => {
      treeCalls.push(force);
      if (force) {
        setTimeout(() => {
          child.signalCode = "SIGTERM";
          child.emit("exit", null, "SIGTERM");
        }, 5);
      }
    },
  });

  expect(treeCalls).toEqual([false, true]);
  expect(directSignals).toEqual([]);
  expect(child.signalCode).toBe("SIGTERM");
});

test("POSIX 真实父子进程组会被完整回收", async () => {
  test.skip(process.platform === "win32", "Windows 使用 taskkill 进程树测试");
  const parent = spawn(process.execPath, [
    "-e",
    [
      "const { spawn } = require('node:child_process');",
      "const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });",
      "process.stdout.write(String(child.pid) + '\\n');",
      "setInterval(() => {}, 1000);",
    ].join(""),
  ], {
    detached: true,
    stdio: ["ignore", "pipe", "ignore"],
  });
  const childPid = await new Promise<number>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("子进程 PID 等待超时")), 2_000);
    parent.stdout?.once("data", (chunk) => {
      clearTimeout(timer);
      resolve(Number(String(chunk).trim()));
    });
    parent.once("error", reject);
  });
  const isAlive = (pid: number): boolean => {
    try {
      process.kill(pid, 0);
      return true;
    } catch (error) {
      return (error as NodeJS.ErrnoException).code !== "ESRCH";
    }
  };

  try {
    await terminateAndWait(parent, {
      gracefulTimeoutMs: 500,
      forceTimeoutMs: 1_000,
      platform: process.platform,
    });
    expect(isAlive(childPid)).toBe(false);
  } finally {
    if (parent.pid !== undefined) {
      try { process.kill(-parent.pid, "SIGKILL"); } catch { /* 已经完整退出 */ }
    }
  }
});
