import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import SearchPage from "./pages/SearchPage";
import SectionPage from "./pages/SectionPage";
import BrowsePage from "./pages/BrowsePage";
import ChatPage from "./pages/ChatPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden" style={{ background: "var(--bg-app)" }}>
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/section/:act/:number" element={<SectionPage />} />
            <Route path="/browse" element={<BrowsePage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
