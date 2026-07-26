import { KeyRound, Mail } from "lucide-react";
import { useApp } from "../context/AppContext";

function Dot({ ok }: { ok: boolean }) {
  return <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-gray-300"}`} />;
}

export default function ConnectionStatus() {
  const { km, email } = useApp();

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 text-gray-600">
        <KeyRound size={16} />
        <Dot ok={km.connected} />
        <span className="truncate">{km.connected ? `KM · ${km.saeId}` : "KM disconnected"}</span>
      </div>
      <div className="flex items-center gap-2 text-gray-600">
        <Mail size={16} />
        <Dot ok={email.connected} />
        <span className="truncate">{email.connected ? email.address : "Mailbox disconnected"}</span>
      </div>
    </div>
  );
}
