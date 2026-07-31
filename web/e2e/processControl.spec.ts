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
