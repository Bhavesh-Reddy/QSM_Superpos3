import type { SecurityLevel } from "../api/client";

const LEVEL_META: Record<SecurityLevel, { label: string; classes: string }> = {
  1: { label: "L1 · OTP", classes: "bg-green-100 text-green-800 border-green-300" },
  2: { label: "L2 · AES", classes: "bg-blue-100 text-blue-800 border-blue-300" },
  3: { label: "L3 · PQC", classes: "bg-purple-100 text-purple-800 border-purple-300" },
  4: { label: "L4 · Plain", classes: "bg-gray-100 text-gray-700 border-gray-300" },
};

interface SecurityBadgeProps {
  level: SecurityLevel | null;
  algorithm?: string | null;
}

export default function SecurityBadge({ level, algorithm }: SecurityBadgeProps) {
  const meta =
    level != null
      ? LEVEL_META[level]
      : { label: "Unencrypted", classes: "bg-gray-100 text-gray-500 border-gray-200" };

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${meta.classes}`}
      title={algorithm ?? undefined}
    >
      {meta.label}
    </span>
  );
}
