import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

// getBaseUrl() caches its result in module state, so we re-import the module
// per test to reset the cache and avoid cross-test interference.
async function loadApi() {
  vi.resetModules()
  const mod = await import("../api")
  return mod as { getBaseUrl: () => Promise<string> }
}

afterEach(() => {
  delete process.env.NEXT_PUBLIC_API_URL
  const w = globalThis.window as any
  if (w && w.appConfig) delete w.appConfig
  if (w && w.__API_PORT__ !== undefined) delete w.__API_PORT__
})

describe("getBaseUrl()", () => {
  it("uses NEXT_PUBLIC_API_URL for a plain web deployment (production backend origin)", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://backend.example.com"
    const { getBaseUrl } = await loadApi()
    expect(await getBaseUrl()).toBe("https://backend.example.com")
  })

  it("never falls back to a machine-localhost backend when NEXT_PUBLIC_API_URL is set", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://backend.example.com"
    const { getBaseUrl } = await loadApi()
    expect(await getBaseUrl()).not.toMatch(/localhost/)
  })

  it("falls back to localhost:8000 only when NEXT_PUBLIC_API_URL is unset (dev only)", async () => {
    const { getBaseUrl } = await loadApi()
    expect(await getBaseUrl()).toBe("http://localhost:8000")
  })

  it("keeps the Electron appConfig branch unchanged (backend target from Electron host)", async () => {
    const w = globalThis.window as any
    w.appConfig = { getApiBaseUrl: () => Promise.resolve("http://127.0.0.1:51000") }
    const { getBaseUrl } = await loadApi()
    expect(await getBaseUrl()).toBe("http://127.0.0.1:51000")
  })
})