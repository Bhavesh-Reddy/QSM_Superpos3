import { Inbox, PenSquare, Settings as SettingsIcon, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ConnectionStatus from "./ConnectionStatus";

export type View = "inbox" | "compose" | "settings";

interface SidebarProps {
  view: View;
  onNavigate: (view: View) => void;
}

const ITEMS: { id: View; label: string; icon: LucideIcon }[] = [
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "compose", label: "Compose", icon: PenSquare },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export default function Sidebar({ view, onNavigate }: SidebarProps) {
  return (
    <aside className="flex h-full w-56 shrink-0 flex-col justify-between border-r border-gray-200 bg-white p-4">
      <div>
        <div className="mb-6 flex items-center gap-2 px-2 text-lg font-semibold text-gray-800">
          <ShieldCheck className="text-indigo-600" size={22} />
          QuMail
        </div>
        <nav className="space-y-1">
          {ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => onNavigate(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                view === id ? "bg-indigo-50 text-indigo-700" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
      </div>
      <div className="border-t border-gray-200 pt-4">
        <ConnectionStatus />
      </div>
    </aside>
  );
}
