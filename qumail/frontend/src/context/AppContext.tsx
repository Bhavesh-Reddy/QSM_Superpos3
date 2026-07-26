import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import * as api from "../api/client";
import type { ETSIStatus, SecurityLevel } from "../api/client";

export interface Alert {
  id: string;
  kind: "error" | "success" | "info";
  message: string;
}

interface KmState {
  connected: boolean;
  connecting: boolean;
  baseUrl: string;
  saeId: string;
  status: ETSIStatus | null;
}

interface EmailState {
  connected: boolean;
  connecting: boolean;
  address: string | null;
  provider: string | null;
}

interface AppContextValue {
  km: KmState;
  email: EmailState;
  defaultLevel: SecurityLevel;
  alerts: Alert[];
  setDefaultLevel: (level: SecurityLevel) => void;
  connectKm: (baseUrl: string, saeId: string, verifyTls: boolean) => Promise<void>;
  connectEmail: (email: string, password: string, provider?: string) => Promise<void>;
  pushAlert: (kind: Alert["kind"], message: string) => void;
  dismissAlert: (id: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

let alertSeq = 0;

export function AppProvider({ children }: { children: ReactNode }) {
  const [km, setKm] = useState<KmState>({
    connected: false,
    connecting: false,
    baseUrl: "http://127.0.0.1:8100",
    saeId: "SAE-ALICE",
    status: null,
  });
  const [email, setEmail] = useState<EmailState>({
    connected: false,
    connecting: false,
    address: null,
    provider: null,
  });
  const [defaultLevel, setDefaultLevel] = useState<SecurityLevel>(2);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const pushAlert = useCallback((kind: Alert["kind"], message: string) => {
    const id = `alert-${++alertSeq}`;
    setAlerts((prev) => [...prev, { id, kind, message }]);
  }, []);

  const dismissAlert = useCallback((id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const connectKm = useCallback(
    async (baseUrl: string, saeId: string, verifyTls: boolean) => {
      setKm((prev) => ({ ...prev, connecting: true }));
      try {
        const status = await api.connectKm({
          base_url: baseUrl,
          sae_id: saeId,
          verify_tls: verifyTls,
        });
        setKm({ connected: true, connecting: false, baseUrl, saeId, status });
        pushAlert(
          "success",
          `Connected to Key Manager · ${status.stored_key_count} keys available.`
        );
      } catch (err) {
        setKm((prev) => ({ ...prev, connected: false, connecting: false }));
        pushAlert(
          "error",
          err instanceof api.ApiError ? err.message : "Failed to connect to Key Manager."
        );
        throw err;
      }
    },
    [pushAlert]
  );

  const connectEmail = useCallback(
    async (address: string, password: string, provider?: string) => {
      setEmail((prev) => ({ ...prev, connecting: true }));
      try {
        const res = await api.connectEmail({
          email: address,
          password,
          provider: provider || null,
        });
        setEmail({
          connected: res.connected,
          connecting: false,
          address: res.address,
          provider: res.provider,
        });
        pushAlert("success", `Mailbox connected: ${res.address} (${res.provider}).`);
      } catch (err) {
        setEmail((prev) => ({ ...prev, connected: false, connecting: false }));
        pushAlert(
          "error",
          err instanceof api.ApiError ? err.message : "Failed to connect mailbox."
        );
        throw err;
      }
    },
    [pushAlert]
  );

  const value = useMemo<AppContextValue>(
    () => ({
      km,
      email,
      defaultLevel,
      alerts,
      setDefaultLevel,
      connectKm,
      connectEmail,
      pushAlert,
      dismissAlert,
    }),
    [km, email, defaultLevel, alerts, connectKm, connectEmail, pushAlert, dismissAlert]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within an AppProvider");
  return ctx;
}
