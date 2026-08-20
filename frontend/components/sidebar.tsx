"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  LayoutDashboard,
  Briefcase,
  Users,
  Video,
  FileText,
  Shield,
  AlertTriangle,
  Settings,
  LogOut,
  ExternalLink,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Job Postings", href: "/jobs", icon: Briefcase },
  { label: "Candidates", href: "/candidates", icon: Users },
  { label: "Interview", href: "/interview", icon: Video },
  { label: "Reports", href: "/reports", icon: FileText },
  { label: "Bias Audit", href: "/bias-audit", icon: Shield },
  { label: "Integrity Log", href: "/integrity", icon: AlertTriangle },
  { label: "Settings", href: "/settings", icon: Settings },
]

interface SidebarProps {
  showLogout?: boolean
}

export default function Sidebar({ showLogout = true }: SidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const [username, setUsername] = useState<string | null>(null)
  useEffect(() => {
    setUsername(localStorage.getItem("username"))
  }, [])

  function handleLogout() {
    localStorage.removeItem("username")
    router.push("/login")
  }

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-64 flex-col bg-sidebar">
      <div className="flex flex-col items-center px-6 py-7">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-white font-bold text-lg">
          IQ
        </div>
        <h1 className="mt-3 text-lg font-semibold text-white tracking-tight">
          InterviewIQ
        </h1>
        <p className="text-xs text-slate-400">AI Assessment Platform</p>
      </div>

      <nav className="mt-2 flex-1 space-y-1 px-3">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/")
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-white"
                  : "text-slate-400 hover:text-white hover:bg-white/10"
              )}
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="my-2 border-t border-white/10" />
      <a
        href="/candidate/entry"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:text-white hover:bg-white/10"
      >
        <ExternalLink className="h-5 w-5 shrink-0" />
        Take Interview
      </a>

      {showLogout && (
        <div className="px-3 pb-5 space-y-3">
          {username && (
            <div className="flex items-center gap-3 rounded-lg px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-semibold">
                {username.charAt(0).toUpperCase()}
              </div>
              <span className="text-sm text-slate-300 truncate">{username}</span>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:text-white hover:bg-white/10"
          >
            <LogOut className="h-5 w-5 shrink-0" />
            Logout
          </button>
        </div>
      )}
    </aside>
  )
}
