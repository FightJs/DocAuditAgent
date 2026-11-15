import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Demo } from "./Demo";

createRoot(document.getElementById("root")!).render(<StrictMode>{import.meta.env.VITE_DEMO === "true" ? <Demo /> : <App />}</StrictMode>);
