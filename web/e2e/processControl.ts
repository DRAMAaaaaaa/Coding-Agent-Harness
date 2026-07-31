import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";

interface TerminableChild extends EventEmitter {
  exitCode: number | null;
  signalCode: NodeJS.Signals | null;
  pid?: number;
  kill(signal?: NodeJS.Signals | number): boolean;
}

interface TerminationOptions {
  gracefulTimeoutMs?: number;
  forceTimeoutMs?: number;
  platform?: NodeJS.Platform;
  windowsTreeTerminator?: WindowsTreeTerminator;
  posixGroupSignaler?: PosixGroupSignaler;
  posixGroupExists?: PosixGroupExists;
}

type WindowsTreeTerminator = (
  pid: number,
  force: boolean,
  timeoutMs: number,
) => Promise<void>;

type PosixGroupSignaler = (processGroupId: number, signal: NodeJS.Signals) => void;
type PosixGroupExists = (processGroupId: number) => boolean;

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

function signalPosixGroup(processGroupId: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-processGroupId, signal);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
  }
}

function posixGroupExists(processGroupId: number): boolean {
  try {
    process.kill(-processGroupId, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

async function waitForPosixTreeExit(
  child: TerminableChild,
  processGroupId: number,
  groupExists: PosixGroupExists,
  timeoutMs: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (hasExited(child) && !groupExists(processGroupId)) return true;
    await new Promise((resolve) => setTimeout(resolve, Math.min(10, timeoutMs)));
  }
  return hasExited(child) && !groupExists(processGroupId);
}

async function terminateWindowsTree(
  pid: number,
  force: boolean,
  timeoutMs: number,
): Promise<void> {
  const arguments_ = ["/PID", String(pid), "/T"];
  if (force) arguments_.push("/F");
  const killer = spawn("taskkill", arguments_, {
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
  const gracefulTimeoutMs = options.gracefulTimeoutMs ?? 1_000;
  const forceTimeoutMs = options.forceTimeoutMs ?? 3_000;
  const platform = options.platform ?? process.platform;

  if (platform === "win32") {
    if (hasExited(child)) return;
    if (child.pid === undefined) throw new Error("Windows 子进程缺少 PID");
    const terminateTree = options.windowsTreeTerminator ?? terminateWindowsTree;
    await terminateTree(child.pid, false, gracefulTimeoutMs);
    if (await waitForExit(child, gracefulTimeoutMs)) return;
    await terminateTree(child.pid, true, forceTimeoutMs);
    if (await waitForExit(child, forceTimeoutMs)) return;
    throw new Error(`子进程 ${child.pid} 在强制终止后仍未退出`);
  }

  if (child.pid === undefined) throw new Error("POSIX 子进程缺少进程组 ID");
  const processGroupId = child.pid;
  const signalGroup = options.posixGroupSignaler ?? signalPosixGroup;
  const groupExists = options.posixGroupExists ?? posixGroupExists;
  if (hasExited(child) && !groupExists(processGroupId)) return;

  signalGroup(processGroupId, "SIGTERM");
  if (
    await waitForPosixTreeExit(
      child,
      processGroupId,
      groupExists,
      gracefulTimeoutMs,
    )
  ) return;

  signalGroup(processGroupId, "SIGKILL");
  if (
    !(await waitForPosixTreeExit(
      child,
      processGroupId,
      groupExists,
      forceTimeoutMs,
    ))
  ) throw new Error(`进程组 ${processGroupId} 在强制终止后仍未退出`);
}
