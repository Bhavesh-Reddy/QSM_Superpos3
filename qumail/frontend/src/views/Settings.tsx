import { useState } from "react";
import type { FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useApp } from "../context/AppContext";
import type { SecurityLevel } from "../api/client";

const LEVEL_OPTIONS: { value: SecurityLevel; label: string }[] = [
  { value: 1, label: "Level 1 — Quantum OTP" },
  { value: 2, label: "Level 2 — Quantum-aided AES" },
  { value: 3, label: "Level 3 — Post-Quantum (PQC)" },
  { value: 4, label: "Level 4 — No encryption" },
];

const inputClasses =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";

export default function Settings() {
  const { km, email, defaultLevel, setDefaultLevel, connectKm, connectEmail } = useApp();

  const [kmBaseUrl, setKmBaseUrl] = useState(km.baseUrl);
  const [kmSaeId, setKmSaeId] = useState(km.saeId);
  const [kmVerifyTls, setKmVerifyTls] = useState(true);

  const [emailAddress, setEmailAddress] = useState(email.address ?? "");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailProvider, setEmailProvider] = useState("");

  async function handleKmSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await connectKm(kmBaseUrl, kmSaeId, kmVerifyTls);
    } catch {
      // Surfaced via AlertList — nothing else to do here.
    }
  }

  async function handleEmailSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await connectEmail(emailAddress, emailPassword, emailProvider || undefined);
      setEmailPassword("");
    } catch {
      // Surfaced via AlertList — nothing else to do here.
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-8">
      <h1 className="text-xl font-semibold text-gray-800">Settings</h1>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Key Manager
        </h2>
        <form onSubmit={handleKmSubmit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">KM base URL</span>
            <input
              value={kmBaseUrl}
              onChange={(e) => setKmBaseUrl(e.target.value)}
              className={inputClasses}
              placeholder="http://127.0.0.1:8100"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">SAE ID</span>
            <input
              value={kmSaeId}
              onChange={(e) => setKmSaeId(e.target.value)}
              className={inputClasses}
              placeholder="SAE-ALICE"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={kmVerifyTls}
              onChange={(e) => setKmVerifyTls(e.target.checked)}
            />
            Verify TLS
          </label>
          <button
            type="submit"
            disabled={km.connecting}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60 ${
              km.connected ? "bg-emerald-600 hover:bg-emerald-500" : "bg-indigo-600 hover:bg-indigo-500"
            }`}
          >
            {km.connecting && <Loader2 size={14} className="animate-spin" />}
            {km.connected ? "Reconnect" : "Connect"}
          </button>
          {km.connected && km.status && (
            <p className="text-xs text-gray-500">
              Connected · {km.status.stored_key_count}/{km.status.max_key_count} keys stored
            </p>
          )}
        </form>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Email Account
        </h2>
        <form onSubmit={handleEmailSubmit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">Email address</span>
            <input
              type="email"
              value={emailAddress}
              onChange={(e) => setEmailAddress(e.target.value)}
              className={inputClasses}
              placeholder="alice@gmail.com"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">App password</span>
            <input
              type="password"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              className={inputClasses}
              autoComplete="off"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-gray-600">Provider (optional — auto-detected)</span>
            <select
              value={emailProvider}
              onChange={(e) => setEmailProvider(e.target.value)}
              className={inputClasses}
            >
              <option value="">Auto-detect</option>
              <option value="gmail">Gmail</option>
              <option value="yahoo">Yahoo</option>
              <option value="outlook">Outlook</option>
            </select>
          </label>
          <button
            type="submit"
            disabled={email.connecting}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60 ${
              email.connected ? "bg-emerald-600 hover:bg-emerald-500" : "bg-indigo-600 hover:bg-indigo-500"
            }`}
          >
            {email.connecting && <Loader2 size={14} className="animate-spin" />}
            {email.connected ? "Reconnect" : "Connect"}
          </button>
          {email.connected && (
            <p className="text-xs text-gray-500">
              Connected as {email.address} ({email.provider})
            </p>
          )}
        </form>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Defaults
        </h2>
        <label className="block text-sm">
          <span className="mb-1 block text-gray-600">Default security level</span>
          <select
            value={defaultLevel}
            onChange={(e) => setDefaultLevel(Number(e.target.value) as SecurityLevel)}
            className={inputClasses}
          >
            {LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </section>
    </div>
  );
}
