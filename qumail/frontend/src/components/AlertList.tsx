import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useApp } from "../context/AppContext";
import type { Alert } from "../context/AppContext";

const KIND_META: Record<Alert["kind"], { icon: LucideIcon; classes: string }> = {
  error: { icon: AlertTriangle, classes: "bg-red-50 text-red-800 border-red-200" },
  success: { icon: CheckCircle2, classes: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  info: { icon: Info, classes: "bg-blue-50 text-blue-800 border-blue-200" },
};

export default function AlertList() {
  const { alerts, dismissAlert } = useApp();

  if (alerts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 flex-col gap-2">
      {alerts.map((alert) => {
        const { icon: Icon, classes } = KIND_META[alert.kind];
        return (
          <div
            key={alert.id}
            className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-md ${classes}`}
          >
            <Icon size={16} className="mt-0.5 shrink-0" />
            <p className="flex-1">{alert.message}</p>
            <button
              type="button"
              onClick={() => dismissAlert(alert.id)}
              className="shrink-0 opacity-60 hover:opacity-100"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
