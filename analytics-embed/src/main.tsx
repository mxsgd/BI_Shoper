import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { STATIC_DEMO } from "./staticDemo";
import { NoSessionError, loadSession } from "./api";
import SessionError from "./components/SessionError";

// GitHub Pages has no SPA fallback, so the static demo routes through the URL hash.
const Router = STATIC_DEMO ? HashRouter : BrowserRouter;

const root = createRoot(document.getElementById("root")!);

// Every API call needs the store from the signed session, so resolve it before the first render.
loadSession().then(
  () =>
    root.render(
      <StrictMode>
        <Router>
          <App />
        </Router>
      </StrictMode>,
    ),
  (err) => root.render(<SessionError noSession={err instanceof NoSessionError && err.message === "no-session"} />),
);
