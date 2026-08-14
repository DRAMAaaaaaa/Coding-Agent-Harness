import type { HarnessApi } from "./types";
import { HarnessWorkbench } from "./workbench/HarnessWorkbench";

interface AppProps { api: HarnessApi; }

export function App({ api }: AppProps) {
  return <HarnessWorkbench api={api} />;
}
