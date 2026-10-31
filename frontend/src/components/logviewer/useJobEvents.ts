/**
 * SSE hook for live job events with Last-Event-ID replay, deduplication, and backoff.
 */
import { useState, useEffect, useRef, useCallback } from "react";

export type EventLevel = "DEBUG" | "INFO" | "WARNING" | "WARN" | "ERROR" | "CRITICAL";

export interface JobEvent {
  id: number | string;
  job_id?: string;
  task_id?: string;
  device?: string;
  level: EventLevel;
  message: string;
  ts?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
}

export interface UseJobEventsResult {
  events: JobEvent[];
  status: "idle" | "connecting" | "open" | "closed" | "error";
  progress: number;
  error: Error | null;
  clear: () => void;
  reconnect: () => void;
}

export function useJobEvents(jobId: string | null | undefined): UseJobEventsResult {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [status, setStatus] = useState<"idle" | "connecting" | "open" | "closed" | "error">(
    "idle"
  );
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<Error | null>(null);

  const seenIdsRef = useRef<Set<string | number>>(new Set());
  const lastEventIdRef = useRef<string | number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);

  const clear = useCallback(() => {
    setEvents([]);
    seenIdsRef.current.clear();
    lastEventIdRef.current = null;
    setProgress(0);
  }, []);

  const connect = useCallback(() => {
    if (!jobId) {
      setStatus("idle");
      return;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setStatus("connecting");
    setError(null);

    const sinceParam = lastEventIdRef.current ? `?since=${lastEventIdRef.current}` : "";
    const url = `/api/v1/jobs/${jobId}/events${sinceParam}`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      setStatus("open");
      retryCountRef.current = 0;
    };

    es.onmessage = (e) => {
      try {
        const rawEvent = JSON.parse(e.data);
        const eventId = rawEvent.id || e.lastEventId || Date.now() + Math.random();

        if (seenIdsRef.current.has(eventId)) {
          return;
        }

        seenIdsRef.current.add(eventId);
        lastEventIdRef.current = eventId;

        const eventItem: JobEvent = {
          id: eventId,
          job_id: rawEvent.job_id || jobId,
          task_id: rawEvent.task_id,
          device: rawEvent.device || rawEvent.hostname,
          level: (rawEvent.level || "INFO").toUpperCase() as EventLevel,
          message: rawEvent.message || "",
          ts: rawEvent.ts || new Date().toISOString(),
          data: rawEvent.data,
        };

        setEvents((prev) => [...prev, eventItem]);

        if (rawEvent.data?.progress !== undefined) {
          setProgress(Number(rawEvent.data.progress));
        }
      } catch (err) {
        console.warn("Failed to parse SSE event data:", err);
      }
    };

    es.onerror = () => {
      setStatus("error");
      setError(new Error("EventSource connection error"));
      es.close();

      // Exponential backoff reconnect
      const backoff = Math.min(1000 * Math.pow(2, retryCountRef.current), 15000);
      retryCountRef.current += 1;

      if (retryCountRef.current <= 5) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, backoff);
      } else {
        setStatus("closed");
      }
    };
  }, [jobId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [connect]);

  return {
    events,
    status,
    progress,
    error,
    clear,
    reconnect: connect,
  };
}
