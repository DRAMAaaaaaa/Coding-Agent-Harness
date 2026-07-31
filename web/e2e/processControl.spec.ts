import { expect, test } from "@playwright/test";
import { EventEmitter } from "node:events";

import { terminateAndWait } from "./processControl";

test("子进程忽略优雅退出时会强制终止并等待退出", async () => {
  const processEvents = new EventEmitter();
  const signals: Array<NodeJS.Signals | number | undefined> = [];
  const child = Object.assign(processEvents, {
    exitCode: null as number | null,
    signalCode: null as NodeJS.Signals | null,
    pid: 42,
    kill(signal?: NodeJS.Signals | number): boolean {
      signals.push(signal);
      if (signal === "SIGKILL") {
        this.signalCode = "SIGKILL";
        this.emit("exit", null, "SIGKILL");
      }
      return true;
    },
  });

  await terminateAndWait(child, {
    gracefulTimeoutMs: 1,
    forceTimeoutMs: 50,
    platform: "linux",
  });

  expect(signals).toEqual([undefined, "SIGKILL"]);
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
