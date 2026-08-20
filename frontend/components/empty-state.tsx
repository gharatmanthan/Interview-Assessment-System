"use client"

import type { LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <Icon className="h-6 w-6 text-slate-400" />
        </div>
      )}
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
