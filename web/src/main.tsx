import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { createBrowserApi } from "./api";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App api={createBrowserApi()} /></StrictMode>,
);
