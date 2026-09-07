import { getBaseUrl } from "./api"
import type {
  LiveServerMessage,
  LiveCandidateState,
  LiveRecruiterState,
} from "./types"

/**
 * Phase 3A: shared live-interview WebSocket client.
 *
 * Both the recruiter (Electron) and the candidate connect to the SAME
 * /api/ws/interview/{session_id} endpoint. The server authenticates the
 * connecting party from its token and routes messages by role; the client
 * never sends a role or session identity (the server derives both).
 */

const CONNECT_TIMEOUT_MS = 10000
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const RECONNECT_JITTER = 0.3

export interface LiveConnectOptions {
  onOpen?: () => void
  onClose?: () => void
  onError?: (err?: unknown) => void
  onMessage: (msg: LiveServerMessage) => void
  onReconnecting?: (attempt: number, delayMs: number) => void
}

export interface LiveConnection {
  ws: WebSocket
  close: () => void
  reconnect: () => Promise<void>
}

/**
 * Recruiter connection. Uses the recruiter Bearer token (the same one used for
 * authenticated fetch calls) passed as ?token=... (browsers can't set headers
 * on WebSocket upgrades).
 */
export async function connectRecruiterLive(
  state: LiveRecruiterState,
  opts: LiveConnectOptions
): Promise<LiveConnection> {
  const base = await getBaseUrl()
  const wsUrl = `${base.replace(/^http/, "ws")}/api/ws/interview/${encodeURIComponent(state.sessionId)}?token=${encodeURIComponent(state.token)}`
  return _createConnection(wsUrl, opts)
}

/**
 * Candidate connection. Uses the candidate's X-Interview-Token value passed as
 * ?token=... (the server distinguishes candidate vs recruiter role from the
 * token type, so the same query-param approach works for both).
 */
export async function connectCandidateLive(
  state: LiveCandidateState,
  opts: LiveConnectOptions
): Promise<LiveConnection> {
  const base = await getBaseUrl()
  const wsUrl = `${base.replace(/^http/, "ws")}/api/ws/interview/${encodeURIComponent(state.sessionId ?? "")}?token=${encodeURIComponent(state.interviewToken)}`
  return _createConnection(wsUrl, opts)
}

function _createConnection(wsUrl: string, opts: LiveConnectOptions): Promise<LiveConnection> {
  return new Promise((resolve, reject) => {
    let ws: WebSocket | null = null
    let reconnectAttempt = 0
    let isClosed = false
    let isConnected = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const clearReconnectTimer = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const scheduleReconnect = () => {
      if (isClosed) return
      clearReconnectTimer()
      const delay = Math.min(
        RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt) + Math.random() * RECONNECT_BASE_MS * RECONNECT_JITTER,
        RECONNECT_MAX_MS
      )
      reconnectAttempt++
      opts.onReconnecting?.(reconnectAttempt, delay)
      reconnectTimer = setTimeout(() => {
        if (!isClosed) {
          _connect()
        }
      }, delay)
    }

    const _connect = () => {
      if (isClosed) return
      ws = new WebSocket(wsUrl)
      let settled = false

const timeout = setTimeout(() => {
        if (settled) return
        settled = true
        ws?.close()
        const err = new Error("WebSocket connection timed out")
        if (!isConnected) {
          opts.onError?.(err)
          reject(err)
        } else {
          opts.onError?.(err)
          scheduleReconnect()
        }
      }, CONNECT_TIMEOUT_MS)

    const settle = (fn: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      fn()
    }

    ws.onopen = () => {
      settle(() => {
        reconnectAttempt = 0
        isConnected = true
        opts.onOpen?.()
        if (conn) resolve(conn)
      })
    }
    ws.onclose = () => {
      if (isClosed) {
        opts.onClose?.()
        return
      }
      if (!isConnected) {
        // Initial connection failed before open
        settle(() => {
          const err = new Error("WebSocket closed before opening")
          opts.onError?.(err)
          reject(err)
        })
        return
      }
      // Connected then closed - schedule reconnect
      opts.onClose?.()
      isConnected = false
      scheduleReconnect()
    }
    ws.onerror = (e) => {
      if (settled) return
      if (!isConnected) {
        // Initial connection error
        settle(() => {
          const err = new Error("WebSocket connection error")
          opts.onError?.(err)
          reject(err)
        })
      } else {
        // Error after connection established
        opts.onError?.(e)
      }
    }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data && typeof data.type === "string") {
            opts.onMessage(data as LiveServerMessage)
          } else {
            opts.onMessage({ type: "error", code: "unknown" } as LiveServerMessage)
          }
        } catch {
          // Ignore non-JSON frames (e.g. ping).
        }
      }
    }

    let conn: LiveConnection | null = null
    conn = {
      get ws() {
        if (!ws) throw new Error("WebSocket not initialized")
        return ws
      },
      close: () => {
        isClosed = true
        clearReconnectTimer()
        ws?.close()
        ws = null
      },
      reconnect: async () => {
        if (isClosed) return
        clearReconnectTimer()
        ws?.close()
        reconnectAttempt = 0
        isConnected = false
        _connect()
      },
    }
    _connect()
  })
}