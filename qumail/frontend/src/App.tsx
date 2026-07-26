import { useState } from "react";
import Sidebar from "./components/Sidebar";
import type { View } from "./components/Sidebar";
import AlertList from "./components/AlertList";
import Inbox from "./views/Inbox";
import Compose from "./views/Compose";
import Settings from "./views/Settings";

export default function App() {
  const [view, setView] = useState<View>("inbox");

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-50 text-gray-900">
      <Sidebar view={view} onNavigate={setView} />
      <main className="flex-1 overflow-y-auto">
        {view === "inbox" && <Inbox />}
        {view === "compose" && <Compose />}
        {view === "settings" && <Settings />}
      </main>
      <AlertList />
    </div>
  );
}
