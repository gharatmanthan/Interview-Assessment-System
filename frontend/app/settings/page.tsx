"use client"

import { useEffect, useState, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Settings, DeviceInfo, GmailStatus, CalendarStatus } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Loader2, Globe, Laptop, Mail, Unlink, CalendarDays } from "lucide-react"

interface ConnectionConfig {
  backendMode: string
  remoteApiUrl: string
  needsSetup: boolean
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [settings, setSettings] = useState<Settings>({
    camera_index: 0,
    mic_device: "",
    llm_provider: "Groq",
    export_dir: "",
    gmail_connected: false,
    gmail_user: "",
    calendar_connected: false,
    calendar_user: "",
    interview_duration_minutes: 45,
    interview_buffer_minutes: 10,
    work_start_hour: 9,
    work_end_hour: 18,
    scheduling_horizon_days: 30,
    working_days: [0, 1, 2, 3, 4],
    excluded_dates: [],
  })

  const [devices, setDevices] = useState<DeviceInfo[]>([])
  const [conn, setConn] = useState<ConnectionConfig | null>(null)
  const [savingConn, setSavingConn] = useState(false)
  const [gmailStatus, setGmailStatus] = useState<GmailStatus>({ connected: false, email: "" })
  const [gmailLoading, setGmailLoading] = useState(false)
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus>({ connected: false, email: "" })
  const [calendarLoading, setCalendarLoading] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [settingsData, deviceList, gmailData, calendarData] = await Promise.all([
        api.getSettings(),
        api.getDevices(),
        api.getGmailStatus(),
        api.getCalendarStatus(),
      ])
      setSettings(settingsData)
      setDevices(deviceList)
      setGmailStatus(gmailData)
      setCalendarStatus(calendarData)
    } catch (err: any) {
      setError(err.message || "Failed to load settings")
      toast.error("Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const loadConnection = useCallback(async () => {
    try {
      const cfg = await (window as any).appConfig?.getConfig?.()
      if (cfg) setConn({ backendMode: cfg.backendMode, remoteApiUrl: cfg.remoteApiUrl || "", needsSetup: cfg.needsSetup })
    } catch {
    }
  }, [])

  useEffect(() => { loadConnection() }, [loadConnection])

  async function handleSaveConnection() {
    if (!conn) return
    setSavingConn(true)
    try {
      const update =
        conn.backendMode === "local"
          ? { backendMode: "local" }
          : { backendMode: "remote", remoteApiUrl: conn.remoteApiUrl.trim().replace(/\/+$/, "") }
      await (window as any).appConfig?.setConfig?.(update)
      toast.success("Connection settings saved")
      if ((window as any).appConfig?.restartWindow) {
        await (window as any).appConfig.restartWindow()
      } else {
        await loadConnection()
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to save connection settings")
    } finally {
      setSavingConn(false)
    }
  }

  const cameras = devices.filter((d) => d.device_class === "camera")
  const microphones = devices.filter((d) => d.device_class === "microphone")

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.updateSettings(settings)
      toast.success("Settings saved successfully")
    } catch (err: any) {
      toast.error(err.message || "Failed to save settings")
    } finally {
      setSaving(false)
    }
  }

  function updateField<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  async function handleGmailConnect() {
    setGmailLoading(true)
    try {
      const result = await api.connectGmail()
      if (result.success) {
        setGmailStatus({ connected: true, email: result.email })
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to connect Gmail")
    } finally {
      setGmailLoading(false)
    }
  }

  async function handleGmailDisconnect() {
    setGmailLoading(true)
    try {
      await api.disconnectGmail()
      setGmailStatus({ connected: false, email: "" })
      toast.success("Gmail disconnected")
    } catch (err: any) {
      toast.error(err.message || "Failed to disconnect Gmail")
    } finally {
      setGmailLoading(false)
    }
  }

  async function handleCalendarConnect() {
    setCalendarLoading(true)
    try {
      const result = await api.connectCalendar()
      if (result.success) {
        setCalendarStatus({ connected: true, email: result.email })
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to connect Calendar")
    } finally {
      setCalendarLoading(false)
    }
  }

  async function handleCalendarDisconnect() {
    setCalendarLoading(true)
    try {
      await api.disconnectCalendar()
      setCalendarStatus({ connected: false, email: "" })
      toast.success("Calendar disconnected")
    } catch (err: any) {
      toast.error(err.message || "Failed to disconnect Calendar")
    } finally {
      setCalendarLoading(false)
    }
  }

  const LLM_PROVIDERS = ["Groq", "OpenAI", "Gemini", "Anthropic", "Ollama"]

const WEEKDAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
]

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-2 text-sm text-muted-foreground">Loading settings...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Settings</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">Configure your interview environment</p>
        </div>

        <Card>
          <CardContent className="p-6">
            <form onSubmit={handleSave} className="space-y-6">
              {conn && (
                <div className="space-y-4">
                  <h3 className="text-sm font-semibold text-foreground">Connection</h3>
                  <p className="text-xs text-muted-foreground">
                    Where interview data lives. Integrity checks always run locally on this machine.
                  </p>
                  <div className="space-y-2">
                    <Label>Backend mode</Label>
                    <Select value={conn.backendMode} onValueChange={(val) => setConn((c) => (c ? { ...c, backendMode: val } : c))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="remote"><span className="flex items-center gap-2"><Globe className="h-4 w-4" /> Remote interview server</span></SelectItem>
                        <SelectItem value="local"><span className="flex items-center gap-2"><Laptop className="h-4 w-4" /> This computer only</span></SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {conn.backendMode === "remote" && (
                    <div className="space-y-2">
                      <Label htmlFor="remote-api-url">Server address</Label>
                      <Input id="remote-api-url" value={conn.remoteApiUrl} onChange={(e) => setConn((c) => (c ? { ...c, remoteApiUrl: e.target.value } : c))} placeholder="https://interviewiq-api.onrender.com" />
                    </div>
                  )}
                  <div className="flex justify-end">
                    <Button type="button" variant="outline" size="sm" onClick={handleSaveConnection} disabled={savingConn}>
                      {savingConn ? (<><Loader2 className="mr-2 h-3 w-3 animate-spin" /> Saving...</>) : ("Save connection")}
                    </Button>
                  </div>
                </div>
              )}

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Device Selection</h3>
                <div className="space-y-2">
                  <Label>Camera</Label>
                  <Select value={String(settings.camera_index)} onValueChange={(val) => updateField("camera_index", Number(val))}>
                    <SelectTrigger><SelectValue placeholder="Select a camera" /></SelectTrigger>
                    <SelectContent>
                      {cameras.length === 0 ? (<SelectItem value="0" disabled>No cameras found</SelectItem>) : (
                        cameras.map((cam) => (<SelectItem key={cam.name} value={String(cam.index ?? 0)}>{cam.name}</SelectItem>))
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Microphone</Label>
                  <Select value={settings.mic_device} onValueChange={(val) => updateField("mic_device", val)}>
                    <SelectTrigger><SelectValue placeholder="Select a microphone" /></SelectTrigger>
                    <SelectContent>
                      {microphones.length === 0 ? (<SelectItem value="none" disabled>No microphones found</SelectItem>) : (
                        microphones.map((mic) => (<SelectItem key={mic.name} value={mic.name}>{mic.name}</SelectItem>))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">LLM Configuration</h3>
                <div className="space-y-2">
                  <Label>Provider</Label>
                  <Select value={settings.llm_provider} onValueChange={(val) => updateField("llm_provider", val)}>
                    <SelectTrigger><SelectValue placeholder="Select provider" /></SelectTrigger>
                    <SelectContent>
                      {LLM_PROVIDERS.map((p) => (<SelectItem key={p} value={p}>{p}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-xs text-muted-foreground">
                  The model API key is read from the server environment (<code>GROQ_API_KEY</code>) and is never stored nor exposed through this app.
                </p>
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Email Integration</h3>
                <p className="text-xs text-muted-foreground">
                  Connect Gmail to automatically screen incoming job applications and invite qualified candidates.
                </p>
                {gmailStatus.connected ? (
                  <div className="flex items-center justify-between rounded-lg border border-success/20 bg-success-bg p-3">
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-success-text" />
                      <span className="text-sm text-success-text">Connected as {gmailStatus.email}</span>
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={handleGmailDisconnect} disabled={gmailLoading} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                      <Unlink className="h-3 w-3 mr-1" /> Disconnect
                    </Button>
                  </div>
                ) : (
                  <Button type="button" variant="outline" onClick={handleGmailConnect} disabled={gmailLoading}>
                    {gmailLoading ? (<><Loader2 className="mr-2 h-3 w-3 animate-spin" /> Connecting...</>) : (<><Mail className="mr-2 h-3 w-3" /> Connect Gmail</>)}
                  </Button>
                )}
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Calendar Integration (Auto-Scheduling)</h3>
                <p className="text-xs text-muted-foreground">
                  Connect Google Calendar so shortlisted candidates are automatically booked into your next free slot and receive the interview date by email.
                </p>
                {calendarStatus.connected ? (
                  <div className="flex items-center justify-between rounded-lg border border-success/20 bg-success-bg p-3">
                    <div className="flex items-center gap-2">
                      <CalendarDays className="h-4 w-4 text-success-text" />
                      <span className="text-sm text-success-text">Connected as {calendarStatus.email}</span>
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={handleCalendarDisconnect} disabled={calendarLoading} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                      <Unlink className="h-3 w-3 mr-1" /> Disconnect
                    </Button>
                  </div>
                ) : (
                  <Button type="button" variant="outline" onClick={handleCalendarConnect} disabled={calendarLoading}>
                    {calendarLoading ? (<><Loader2 className="mr-2 h-3 w-3 animate-spin" /> Connecting...</>) : (<><CalendarDays className="mr-2 h-3 w-3" /> Connect Google Calendar</>)}
                  </Button>
                )}
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Interview Scheduling</h3>
                <p className="text-xs text-muted-foreground">
                  These preferences determine how the next available interview slot is chosen from your calendar.
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="duration">Interview duration (min)</Label>
                    <Input id="duration" type="number" min={15} max={180} value={settings.interview_duration_minutes} onChange={(e) => updateField("interview_duration_minutes", Number(e.target.value))} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="buffer">Buffer between slots (min)</Label>
                    <Input id="buffer" type="number" min={0} max={60} value={settings.interview_buffer_minutes} onChange={(e) => updateField("interview_buffer_minutes", Number(e.target.value))} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="work-start">Work start hour</Label>
                    <Input id="work-start" type="number" min={0} max={23} value={settings.work_start_hour} onChange={(e) => updateField("work_start_hour", Number(e.target.value))} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="work-end">Work end hour</Label>
                    <Input id="work-end" type="number" min={0} max={23} value={settings.work_end_hour} onChange={(e) => updateField("work_end_hour", Number(e.target.value))} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="horizon">Scheduling horizon (days)</Label>
                    <Input id="horizon" type="number" min={1} max={90} value={settings.scheduling_horizon_days} onChange={(e) => updateField("scheduling_horizon_days", Number(e.target.value))} />
                  </div>
                  <div className="space-y-2 col-span-2">
                    <Label>Working days</Label>
                    <div className="flex flex-wrap gap-2">
                      {WEEKDAYS.map((d) => {
                        const active = settings.working_days.includes(d.value)
                        return (
                          <button
                            key={d.value}
                            type="button"
                            onClick={() => {
                              const next = active
                                ? settings.working_days.filter((v) => v !== d.value)
                                : [...settings.working_days, d.value].sort()
                              updateField("working_days", next)
                            }}
                            className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                              active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-muted-foreground"
                            }`}
                          >
                            {d.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <div className="space-y-2 col-span-2">
                    <Label htmlFor="excluded-dates">Excluded dates (holidays, comma-separated YYYY-MM-DD)</Label>
                    <Input id="excluded-dates" value={settings.excluded_dates.join(", ")} onChange={(e) => updateField("excluded_dates", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} placeholder="2026-12-25, 2026-01-01" />
                  </div>
                </div>
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Export Directory</h3>
                <div className="space-y-2">
                  <Label htmlFor="export-dir">Export Directory</Label>
                  <Input id="export-dir" value={settings.export_dir} onChange={(e) => updateField("export_dir", e.target.value)} placeholder="/path/to/export" />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={saving}>{saving ? "Saving..." : "Save Settings"}</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
