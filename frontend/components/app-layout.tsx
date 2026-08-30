"use client"

import { usePathname } from "next/navigation"
import Sidebar from "@/components/sidebar"
import { FirstRunGate } from "@/components/first-run-gate"

const NO_SIDEBAR_ROUTES = ["/login", "/", "/apply"]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isCandidateRoute = pathname.startsWith("/candidate")
  const showSidebar = !isCandidateRoute && !NO_SIDEBAR_ROUTES.includes(pathname)

  return (
    <FirstRunGate>
      <div className="flex min-h-screen">
        {showSidebar && <Sidebar />}
        <main className={`flex-1 ${showSidebar ? "ml-64" : ""}`}>
          {children}
        </main>
      </div>
    </FirstRunGate>
  )
}
