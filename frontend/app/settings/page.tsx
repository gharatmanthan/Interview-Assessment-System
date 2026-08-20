"use client"

import { useEffect, useState, useCallback } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Settings, DeviceInfo } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Loader2, Eye, EyeOff } from "lucide-react"

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showApiKey, setShowApiKey] = useState(false)

  const [settings, setSettings] = useState<Settings>({
    camera_index: 0,
    mic_device: "",
    llm_provider: "Groq",
    llm_api_key: "",
    export_dir: "",
  })

  const [devices, setDevices] = useState<DeviceInfo[]>([])

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [settingsData, deviceList] = await Promise.all([api.getSettings(), api.getDevices()])
      setSettings(settingsData)
      setDevices(deviceList)
    } catch (err: any) {
      setError(err.message || "Failed to load settings")
      toast.error("Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

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

  const LLM_PROVIDERS = ["Groq", "OpenAI", "Gemini", "Anthropic", "Ollama"]

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-custom">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-2 text-sm text-slate-500">Loading settings...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-custom">
        <div className="text-center">
          <p className="text-sm text-red-500">{error}</p>
          <Button variant="outline" className="mt-4" onClick={fetchData}>Retry</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-custom p-8">
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500">Configure your interview environment</p>
        </div>

        <Card className="bg-white">
          <CardContent className="p-6">
            <form onSubmit={handleSave} className="space-y-6">
              {/* Device Selection */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-900">Device Selection</h3>
                <div className="space-y-2">
                  <Label>Camera</Label>
                  <Select
                    value={String(settings.camera_index)}
                    onValueChange={(val) => updateField("camera_index", Number(val))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a camera" />
                    </SelectTrigger>
                    <SelectContent>
                      {cameras.length === 0 ? (
                        <SelectItem value="0" disabled>No cameras found</SelectItem>
                      ) : (
                        cameras.map((cam) => (
                          <SelectItem key={cam.name} value={String(cam.index ?? 0)}>
                            {cam.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Microphone</Label>
                  <Select
                    value={settings.mic_device}
                    onValueChange={(val) => updateField("mic_device", val)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select a microphone" />
                    </SelectTrigger>
                    <SelectContent>
                      {microphones.length === 0 ? (
                        <SelectItem value="none" disabled>No microphones found</SelectItem>
                      ) : (
                        microphones.map((mic) => (
                          <SelectItem key={mic.name} value={mic.name}>
                            {mic.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              {/* LLM Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-900">LLM Configuration</h3>
                <div className="space-y-2">
                  <Label>Provider</Label>
                  <Select
                    value={settings.llm_provider}
                    onValueChange={(val) => updateField("llm_provider", val)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {LLM_PROVIDERS.map((p) => (
                        <SelectItem key={p} value={p}>{p}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="llm-api-key">API Key</Label>
                  <div className="relative">
                    <Input
                      id="llm-api-key"
                      type={showApiKey ? "text" : "password"}
                      value={settings.llm_api_key}
                      onChange={(e) => updateField("llm_api_key", e.target.value)}
                      placeholder="Enter your API key"
                      className="pr-10"
                    />
                    <button
                      type="button"
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 hover:text-slate-600"
                      onClick={() => setShowApiKey(!showApiKey)}
                    >
                      {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Export Directory */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-900">Export Directory</h3>
                <div className="space-y-2">
                  <Label htmlFor="export-dir">Export Directory</Label>
                  <Input
                    id="export-dir"
                    value={settings.export_dir}
                    onChange={(e) => updateField("export_dir", e.target.value)}
                    placeholder="/path/to/export"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : "Save Settings"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
