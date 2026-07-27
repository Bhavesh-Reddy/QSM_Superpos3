import { useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { useApp } from "../context/AppContext";
import { ApiError, fetchMail, readMail } from "../api/client";
import type { MessageSummary, ReadResponse } from "../api/client";
import SecurityBadge from "../components/SecurityBadge";

export default function Inbox() {
  const { email, pushAlert } = useApp();
  const [messages, setMessages] = useState<MessageSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [opened, setOpened] = useState<ReadResponse | null>(null);
  const [opening, setOpening] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await fetchMail("INBOX", 50);
      setMessages(res.messages);
    } catch (err) {
      pushAlert("error", err instanceof ApiError ? err.message : "Failed to fetch inbox.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (email.connected) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email.connected]);

  async function openMessage(index: number) {
    setSelected(index);
    setOpened(null);
    setOpening(true);
    try {
      const result = await readMail({ message_id: messages[index].message_id });
      setOpened(result);
    } catch (err) {
      pushAlert("error", err instanceof ApiError ? err.message : "Failed to open message.");
    } finally {
      setOpening(false);
    }
  }

  if (!email.connected) {
    return (
      <div className="p-8 text-sm text-gray-500">
        Connect your mailbox in Settings to see your inbox.
      </div>
    );
  }

  const activeMessage = selected !== null ? messages[selected] : null;

  return (
    <div className="flex h-full">
      <div className="w-96 shrink-0 overflow-y-auto border-r border-gray-200">
        <div className="flex items-center justify-between border-b border-gray-200 p-4">
          <h1 className="text-lg font-semibold text-gray-800">Inbox</h1>
          <button
            type="button"
            onClick={() => void load()}
            className="text-gray-500 hover:text-gray-700"
            title="Refresh"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </button>
        </div>
        {messages.length === 0 && !loading && (
          <p className="p-4 text-sm text-gray-400">No messages.</p>
        )}
        <ul>
          {messages.map((m, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => void openMessage(i)}
                className={`flex w-full flex-col gap-1 border-b border-gray-100 p-4 text-left hover:bg-gray-50 ${
                  selected === i ? "bg-indigo-50" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-gray-800">{m.sender}</span>
                  <SecurityBadge level={m.level} algorithm={m.algorithm} />
                </div>
                <span className="truncate text-sm text-gray-600">{m.subject || "(no subject)"}</span>
                <span className="text-xs text-gray-400">{new Date(m.timestamp).toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        {selected === null && <p className="text-sm text-gray-400">Select a message to read it.</p>}
        {opening && <Loader2 className="animate-spin text-gray-400" />}
        {opened && activeMessage && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-gray-800">
                {activeMessage.subject || "(no subject)"}
              </h2>
              <SecurityBadge
                level={opened.level}
                algorithm={opened.metadata?.algorithm as string | undefined}
              />
            </div>
            <p className="text-sm text-gray-500">From {activeMessage.sender}</p>
            {opened.metadata?.key_id ? (
              <p className="text-xs font-medium text-emerald-600">
                verified with key {String(opened.metadata.key_id)}
              </p>
            ) : null}
            <div className="whitespace-pre-wrap rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-800">
              {opened.body}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
