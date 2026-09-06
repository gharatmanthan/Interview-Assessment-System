import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// The live.ts module calls getBaseUrl() which caches module state, so we
// re-import per test to get a fresh cache + fresh connect functions.
async function loadLive() {
  vi.resetModules()
  const mod = await import("../live")
  return mod as typeof import("../live")
}

// Fake WebSocket that lets the test drive open/error/close events.
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((e?: unknown) => void) | null = null
  onmessage: ((e: unknown) => void) | null = null
  sent: string[] = []

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  static triggerError(ws: FakeWebSocket) {
    ws.readyState = 3
    ws.onerror?.({ type: "error" })
  }

  static triggerClose(ws: FakeWebSocket) {
    ws.readyState = 3
    ws.onclose?.()
  }
}

beforeEach(() => {
  FakeWebSocket.instances = []
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// connectRecruiterLive is async: it awaits getBaseUrl() before constructing the
// WebSocket. These helpers flush microtasks until the constructor has run.
function lastInstance(): FakeWebSocket {
  return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
}
async function flush(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

describe("connectRecruiterLive WebSocket error handling", () => {
  it("resolves with the socket on open", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket)
    const { connectRecruiterLive } = await loadLive()

    const onOpen = vi.fn()
    const onMessage = vi.fn()
    const wsPromise = connectRecruiterLive(
      { sessionId: "s1", token: "tok" },
      { onOpen, onMessage }
    )

    await flush()
    const ws = lastInstance()
    expect(ws).toBeDefined()
    ws.onopen!()

    const resolved = await wsPromise
    expect(resolved).toBe(ws)
    expect(onOpen).toHaveBeenCalledTimes(1)
    expect(ws.url).toContain("/api/ws/interview/s1")
  })

  it("rejects the promise (no hang) when the socket errors before opening", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket)
    const { connectRecruiterLive } = await loadLive()

    const onError = vi.fn()
    const wsPromise = connectRecruiterLive(
      { sessionId: "s1", token: "tok" },
      { onError, onMessage: vi.fn() }
    )

    await flush()
    FakeWebSocket.triggerError(lastInstance())

    await expect(wsPromise).rejects.toThrow("WebSocket connection error")
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it("rejects the promise (no hang) when the socket closes before opening", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket)
    const { connectRecruiterLive } = await loadLive()

    const onError = vi.fn()
    const wsPromise = connectRecruiterLive(
      { sessionId: "s1", token: "tok" },
      { onError, onMessage: vi.fn() }
    )

    await flush()
    FakeWebSocket.triggerClose(lastInstance())

    await expect(wsPromise).rejects.toThrow("WebSocket closed before opening")
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it("rejects with a timeout when the socket never opens and never errors", async () => {
    vi.useFakeTimers()
    vi.stubGlobal("WebSocket", FakeWebSocket)
    const { connectRecruiterLive } = await loadLive()

    const onError = vi.fn()
    const wsPromise = connectRecruiterLive(
      { sessionId: "s1", token: "tok" },
      { onError, onMessage: vi.fn() }
    )

    await flush()
    const rejection = expect(wsPromise).rejects.toThrow("timed out")
    await vi.advanceTimersByTimeAsync(10001)
    await rejection
    expect(onError).toHaveBeenCalledTimes(1)
  })
})
