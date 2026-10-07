import { Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { AboutPage } from "./pages/AboutPage";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { StockPage } from "./pages/StockPage";

// Three routes (ENGINEERING.md 23.1) plus a not-found page.
export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="stocks/:ticker" element={<StockPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
