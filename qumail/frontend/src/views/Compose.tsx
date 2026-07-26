import { useState } from "react";
import type { FormEvent } from "react";
import { Loader2, Send, TriangleAlert } from "lucide-react";
import { useApp } from "../context/AppContext";
import { ApiError, sendMail } from "../api/client";
import type { SecurityLevel } from "../api/client";

const LEVEL_OPTIONS: { value: SecurityLevel; label: string }[] = [
  { value: 1, label: "Level 1 — Quantum OTP" },
  { value: 2, label: "Level 2 — Quantum-aided AES" },
  { value: 3, label: "Level 3 — Post-Quantum (PQC)" },
  { value: 4, label: "Level 4 — No encryption" },
];

const inputClasses =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";

export default function Compose() {
  const { km, defaultLevel, pushAlert } = useApp();
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [level, setLevel] = useState<SecurityLevel>(defaultLevel);
  const [sending, setSending] = useState(false);

  const showKmWarning = (level === 1 || level === 2) && !km.connected;

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      const result = await sendMail({ to, subject, body, level });
      pushAlert(
        "success",
        result.key_id ? `Sent · key ${result.key_id}` : `Sent (message ${result.message_id})`
      );
      setTo("");
      setSubject("");
      setBody("");
    } catch (err) {
      pushAlert("error", err instanceof ApiError ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-8">
      <h1 className="text-xl font-semibold text-gray-800">Compose</h1>

      {showKmWarning && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <TriangleAlert size={16} className="shrink-0" />
          This level needs the Key Manager, and it isn&apos;t connected. Connect it in Settings
          before sending.
        </div>
      )}

      <form onSubmit={handleSend} className="space-y-3 rounded-xl border border-gray-200 bg-white p-6">
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">To</span>
          <input
            required
            type="email"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className={inputClasses}
            placeholder="bob@example.com"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Subject</span>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className={inputClasses}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Security level</span>
          <select
            value={level}
            onChange={(e) => setLevel(Number(e.target.value) as SecurityLevel)}
            className={inputClasses}
          >
            {LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Body</span>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            className={inputClasses}
          />
        </label>
        <button
          type="submit"
          disabled={sending}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          Send
        </button>
      </form>
    </div>
  );
}
