import { useEffect, useRef, useState } from 'react';

interface UseSSEOptions<T> {
  url: string;
  event?: string;
  enabled?: boolean;
  onMessage?: (data: T) => void;
}

export function useSSE<T>({ url, event = 'message', enabled = true, onMessage }: UseSSEOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setConnected(true);
    source.onerror = () => {
      setConnected(false);
      setError('Connection lost');
    };

    source.addEventListener(event, (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as T;
        setData(parsed);
        setError(null);
        onMessage?.(parsed);
      } catch {
        setError('Failed to parse SSE data');
      }
    });

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [url, event, enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setConnected(false);
  };

  return { data, error, connected, close };
}
