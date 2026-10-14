import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";

const root = document.getElementById("root");
if (!root) throw new Error("Elemento #root ausente em index.html");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
