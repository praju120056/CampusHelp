"use client";
// Server-Sent Events from FastAPI. EventSource reconnects by itself; we refetch on every event.
import { useEffect, useRef, useState } from "react";
import { apiBase } from "./api";
import { getToken } from "./auth";

const EVENT_TYPES: Record<string, string[]> = {
  tickets: ["ticket.created", "ticket.updated", "ticket.escalated"],
  logs: ["log.saved"],
  adjustments: ["adjustment.created", "adjustment.updated"],
};

export type LiveState = "connecting" | "live" | "offline";

export function useLive(channels: string[], onEvent: (type: string, data: Record<string, unknown>) => void): LiveState {
  const handler = useRef(onEvent);
  const [state, setState] = useState<LiveState>("connecting");
  useEffect(() => {
    handler.current = onEvent;
  });
  const key = channels.join(",");

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const sources = key.split(",").map((channel) => {
      const es = new EventSource(`${apiBase()}/stream/${channel}?token=${encodeURIComponent(token)}`);
      es.onopen = () => setState("live");
      es.onerror = () => setState(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
      for (const type of EVENT_TYPES[channel] ?? []) {
        es.addEventListener(type, (e) => {
          let data = {};
          try {
            data = JSON.parse((e as MessageEvent).data || "{}");
          } catch {
            /* ignore */
          }
          handler.current(type, data);
        });
      }
      return es;
    });
    return () => sources.forEach((es) => es.close());
  }, [key]);

  return state;
}

/** Calls fn now and every `ms` milliseconds while the page is open. */
export function useInterval(fn: () => void, ms: number): void {
  const saved = useRef(fn);
  useEffect(() => {
    saved.current = fn;
  });
  useEffect(() => {
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}
