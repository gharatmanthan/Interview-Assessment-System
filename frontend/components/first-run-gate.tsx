"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { Loader2 } from "lucide-react"

/**
 * First-run gate for remote mode.
 *
 * If this desktop app is set to talk to a central server but no server
 * address has been configured yet (fresh install without a baked-in URL),
 * everything routes to /setup until the address is saved. Local mode and
 * configured remote installs pass straight through, so on-site single-
 * machine use behaves exactly as before.
 *
 * Outside Electron (plain `next dev` in a browser tab) there is no config
 * bridge and the gate is inert — that path exists only as a dev convenience.
 */
export function FirstRunGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const appConfig = (window as any).appConfig
        if (!appConfig?.getConfig) {
          setReady(true)
          return
        }
        const cfg = await appConfig.getConfig()
        if (!cancelled && cfg?.needsSetup && pathname !== "/setup") {
          router.replace("/setup")
          return
        }
        if (!cancelled) setReady(true)
      } catch {
        if (!cancelled) setReady(true)
      }
    }
    check()
    return () => { cancelled = true }
  }, [pathname, router])

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  return <>{children}</>
}
