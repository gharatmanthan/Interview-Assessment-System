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

export interface LiveConnectOptions {
  onOpen?: () => void
  onClose?: () => void
  onError?: (err?: unknown) => void
  onMessage: (msg: LiveServerMessage) => void
}

/**
 * Recruiter connection. Uses the recruiter Bearer token (the same one used for
 * authenticated fetch calls) passed as ?token=... (browsers can't set headers
 * on WebSocket upgrades).
 */
export async function connectRecruiterLive(
  state: LiveRecruiterState,
  opts: LiveConnectOptions
): Promise<WebSocket> {
  const base = await getBaseUrl()
  const wsUrl = `${base.replace(/^http/, "ws")}/api/ws/interview/${encodeURIComponent(state.sessionId)}?token=${encodeURIComponent(state.token)}`
  return _open(wsUrl, opts)
}

/**
 * Candidate connection. Uses the candidate's X-Interview-Token value passed as
 * ?token=... (the server distinguishes candidate vs recruiter role from the
 * token type, so the same query-param approach works for both).
 */
export async function connectCandidateLive(
  state: LiveCandidateState,
  opts: LiveConnectOptions
): Promise<WebSocket> {
  const base = await getBaseUrl()
  const wsUrl = `${base.replace(/^http/, "ws")}/api/ws/interview/${encodeURIComponent(state.sessionId ?? "")}?token=${encodeURIComponent(state.interviewToken)}`
  return _open(wsUrl, opts)
}

function _open(wsUrl: string, opts: LiveConnectOptions): Promise<WebSocket> {
  return new Promise<WebSocket>((resolve, reject) => {
    const ws = new WebSocket(wsUrl)
    let settled = false

    const timeout = setTimeout(() => {
      if (settled) return
      settled = true
      ws.close()
      const err = new Error("WebSocket connection timed out")
      opts.onError?.(err)
      reject(err)
    }, CONNECT_TIMEOUT_MS)

    const settle = (fn: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      fn()
    }

    ws.onopen = () => {
      settle(() => {
        opts.onOpen?.()
        resolve(ws)
      })
    }
    ws.onclose = () => {
      if (settled) {
        opts.onClose?.()
        return
      }
      // Unexpected close before the connection opened — reject so awaiting
      // callers get an error instead of hanging indefinitely.
      settle(() => {
        opts.onError?.(new Error("WebSocket closed before opening"))
        opts.onClose?.()
        reject(new Error("WebSocket closed before opening"))
      })
    }
    ws.onerror = (e) => {
      if (settled) return
      settle(() => {
        opts.onError?.(e)
        reject(new Error("WebSocket connection error"))
      })
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
  })
}
