import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { initTheme } from "./utils/theme";
import "./styles/tokens.css";
import "./styles/typography.css";
import "./styles/base.css";

// Тема выставляется до первого рендера, чтобы не мигнуть светлой.
initTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
