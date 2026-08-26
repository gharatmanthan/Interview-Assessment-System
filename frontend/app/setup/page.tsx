"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Loader2, Server, CheckCircle, AlertTriangle, Globe, Laptop } from "lucide-react"

interface AppConfigState {
  backendMode: string
  remoteApiUrl: string
  needsSetup: boolean
}

export default function SetupPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<null | "ok" | "fail">(null)

  const [mode, setMode] = useState("remote")
  const [serverUrl, setServerUrl] = useState("")

  useEffect(() => {
    async function init() {
      try {
        const cfg = (window as any).appConfig?.getConfig
          ? await (window as any).appConfig.getConfig()
          : null
        if (cfg) {
          setMode(cfg.backendMode)
          setServerUrl(cfg.remoteApiUrl || "")
        }
      } catch {}
      setLoading(false)
    }
    init()
  }, [])

  async function handleTest() {
    if (!serverUrl.trim()) return
    setTesting(true)
    setTestResult(null)
    try {
      const target = normalizeUrl(serverUrl)
      const res = await fetch(`${target}/health`, { signal: AbortSignal.timeout(8000) })
      setTestResult(res.ok ? "ok" : "fail")
    } catch {
      setTestResult("fail")
    } finally {
      setTesting(false)
    }
  }

  function normalizeUrl(url: string): string {
    let trimmed = url.trim().replace(/\/+$/, "")
    if (!/^https?:\/\//.test(trimmed)) trimmed = `https://${trimmed}`
    return trimmed
  }

  async function handleSave() {
    setSaving(true)
    try {
      const update =
        mode === "local"
          ? { backendMode: "local" }
          : { backendMode: "remote", remoteApiUrl: normalizeUrl(serverUrl) }
      await (window as any).appConfig?.setConfig?.(update)
      toast.success("Connection settings saved")
      if ((window as any).appConfig?.restartWindow) {
        await (window as any).appConfig.restartWindow()
      } else {
        router.push("/")
      }
    } catch {
      toast.error("Failed to save settings")
    } finally {
      setSaving(false)
    }
  }

  const canSave = mode === "local" || serverUrl.trim().length > 0

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md rounded-2xl shadow-lg">
        <CardContent className="p-8">
          <div className="mb-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Server className="h-6 w-6" />
            </div>
            <h1 className="mt-4 text-2xl font-bold text-foreground">Connect to Interview Server</h1>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              One-time setup. Integrity checks always run locally on this machine regardless of choice.
            </p>
          </div>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>Where is the interview data stored?</Label>
              <Select value={mode} onValueChange={setMode}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="remote"><span className="flex items-center gap-2"><Globe className="h-4 w-4" /> Remote interview server</span></SelectItem>
                  <SelectItem value="local"><span className="flex items-center gap-2"><Laptop className="h-4 w-4" /> This computer only</span></SelectItem>
                </SelectContent>
              </Select>
            </div>

            {mode === "remote" && (
              <div className="space-y-2">
                <Label htmlFor="server-url">Interview server address</Label>
                <Input
                  id="server-url"
                  value={serverUrl}
                  onChange={(e) => { setServerUrl(e.target.value); setTestResult(null) }}
                  placeholder="e.g. https://interviewiq-api.onrender.com"
                />
                <div className="flex items-center justify-between pt-1">
                  <Button type="button" variant="outline" size="sm" onClick={handleTest} disabled={!serverUrl.trim() || testing}>
                    {testing ? (<><Loader2 className="mr-2 h-3 w-3 animate-spin" /> Testing...</>) : ("Test connection")}
                  </Button>
                  {testResult === "ok" && (
                    <Badge variant="success">
                      <CheckCircle className="h-3 w-3 mr-1" />Server reachable
                    </Badge>
                  )}
                  {testResult === "fail" && (
                    <Badge variant="destructive">
                      <AlertTriangle className="h-3 w-3 mr-1" />Unreachable
                    </Badge>
                  )}
                </div>
              </div>
            )}

            <Button className="w-full" size="lg" disabled={!canSave || saving} onClick={handleSave}>
              {saving ? "Saving..." : "Save and Continue"}
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              You can change this later in Settings → Connection
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
