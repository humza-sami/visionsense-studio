import { useEffect, useRef, useState } from 'react'
import { useStore } from '@/store/useStore'

const MAX_RETRY_DELAY = 30_000
const INITIAL_RETRY_DELAY = 1_000

export function useTelemetryWS(backendUrl: string) {
  const updateTelemetry = useStore((s) => s.updateTelemetry)
  const addAlert = useStore((s) => s.addAlert)
  const [connected, setConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)

  useEffect(() => {
    unmountedRef.current = false

    function connect() {
      if (unmountedRef.current) return

      const wsUrl = backendUrl.replace(/^http/, 'ws') + '/ws/telemetry'
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (unmountedRef.current) { ws.close(); return }
        setConnected(true)
        retryDelayRef.current = INITIAL_RETRY_DELAY
      }

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string)
          updateTelemetry(data)
          setLastUpdate(new Date())

          // Extract alerts
          if (Array.isArray(data.alerts)) {
            for (const alert of data.alerts as Array<{ type: string; ts: number; detail: string }>) {
              addAlert({
                cam_id: data.cam_id as string,
                type: alert.type,
                detail: alert.detail,
                ts: alert.ts,
              })
            }
          }
        } catch {
          // Ignore malformed messages
        }
      }

      ws.onerror = () => {
        setConnected(false)
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        if (!unmountedRef.current) {
          const delay = retryDelayRef.current
          retryDelayRef.current = Math.min(delay * 2, MAX_RETRY_DELAY)
          timeoutRef.current = setTimeout(connect, delay)
        }
      }
    }

    connect()

    return () => {
      unmountedRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      wsRef.current?.close()
    }
  }, [backendUrl, updateTelemetry, addAlert])

  return { connected, lastUpdate }
}
