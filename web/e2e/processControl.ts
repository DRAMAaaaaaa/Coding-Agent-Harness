import { spawn, type ChildProcess } from "node:child_process";

type TerminableChild = Pick<
  ChildProcess,
  "exitCode" | "signalCode" | "pid" | "kill" | "once" | "off"
>;

interface TerminationOptions {
  gracefulTimeoutMs?: number;
  forceTimeoutMs?: number;
  platform?: NodeJS.Platform;
}

function hasExited(child: TerminableChild): boolean {
  return child.exitCode !== null || child.signalCode !== null;
}

async function waitForExit(child: TerminableChild, timeoutMs: number): Promise<boolean> {
  if (hasExited(child)) return true;
  return await new Promise<boolean>((resolve) => {
    const finish = (exited: boolean): void => {
      clearTimeout(timer);
      child.off("exit", onExit);
      child.off("error", onError);
      resolve(exited);
    };
    const onExit = (): void => finish(true);
    const onError = (): void => finish(true);
    child.once("exit", onExit);
    child.once("error", onError);
    const timer = setTimeout(() => finish(hasExited(child)), timeoutMs);
  });
}

async function forceTerminateWindows(pid: number, timeoutMs: number): Promise<void> {
  const killer = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
    stdio: "ignore",
    windowsHide: true,
  });
  await new Promise<void>((resolve) => {
    const finish = (): void => {
      clearTimeout(timer);
      killer.off("exit", finish);
      killer.off("error", finish);
      resolve();
    };
    killer.once("exit", finish);
    killer.once("error", finish);
    const timer = setTimeout(() => {
      killer.kill();
      finish();
    }, timeoutMs);
  });
}

export async function terminateAndWait(
  child: TerminableChild,
  options: TerminationOptions = {},
): Promise<void> {
  if (hasExited(child)) return;
  const gracefulTimeoutMs = options.gracefulTimeoutMs ?? 1_000;
  const forceTimeoutMs = options.forceTimeoutMs ?? 3_000;
  const platform = options.platform ?? process.platform;

  child.kill();
  if (await waitForExit(child, gracefulTimeoutMs)) return;

  if (platform === "win32" && child.pid !== undefined) {
    await forceTerminateWindows(child.pid, forceTimeoutMs);
  } else {
    child.kill("SIGKILL");
  }
  if (!(await waitForExit(child, forceTimeoutMs))) {
    throw new Error(`子进程 ${child.pid ?? "unknown"} 在强制终止后仍未退出`);
  }
}
