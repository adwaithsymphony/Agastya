import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ToastProvider } from "./components/ui";
import "./index.css";
import { AuthProvider } from "./lib/auth";
import { Router } from "./lib/router";
import { I18nProvider } from "./lib/i18n";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
    <Router>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </Router>
    </I18nProvider>
  </StrictMode>,
);
