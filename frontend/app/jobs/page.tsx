"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { JobPosting } from "@/lib/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/slider"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Pencil, Trash2, Plus, Briefcase } from "lucide-react"
import { SkillTagInput } from "@/components/skill-tag-input"
import { EmptyState } from "@/components/empty-state"

const COMPETENCY_KEYS = [
  "dsa",
  "system_design",
  "communication",
  "domain_knowledge",
  "problem_solving",
] as const

const COMPETENCY_LABELS: Record<string, string> = {
  dsa: "DSA",
  system_design: "System Design",
  communication: "Communication",
  domain_knowledge: "Domain Knowledge",
  problem_solving: "Problem Solving",
}

const EXPERIENCE_LEVELS = ["Fresher", "Junior", "Mid", "Senior"]

const DEPARTMENTS = ["Software/CS", "Data/ML", "Electronics", "Mechanical", "Civil", "Other"]

const EMPTY_WEIGHTS: Record<string, number> = {
  dsa: 20,
  system_design: 20,
  communication: 20,
  domain_knowledge: 20,
  problem_solving: 20,
}

function emptyForm(): Omit<JobPosting, "job_id"> {
  return {
    title: "",
    description: "",
    required_skills: [],
    experience_level: "Mid",
    department: "",
    num_rounds: 5,
    time_limit_seconds: 300,
    adaptive_difficulty: true,
    competency_weights: { ...EMPTY_WEIGHTS },
  }
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobPosting[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(emptyForm())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<JobPosting | null>(null)

  async function fetchJobs() {
    try {
      const data = await api.getJobs()
      setJobs(data)
    } catch (err: any) {
      toast.error(err.message || "Failed to load jobs")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
  }, [])

  const weightSum = Object.values(form.competency_weights).reduce(
    (a, b) => a + b,
    0
  )
  const weightsValid = weightSum === 100

  function openCreate() {
    setForm(emptyForm())
    setEditing(false)
    setEditingId(null)
    setShowForm(true)
  }

  function openEdit(job: JobPosting) {
    setForm({
      title: job.title,
      description: job.description,
      required_skills: [...job.required_skills],
      experience_level: job.experience_level,
      department: job.department,
      num_rounds: job.num_rounds,
      time_limit_seconds: job.time_limit_seconds,
      adaptive_difficulty: job.adaptive_difficulty,
      competency_weights: { ...job.competency_weights },
    })
    setEditing(true)
    setEditingId(job.job_id)
    setShowForm(true)
  }

  function cancelForm() {
    setShowForm(false)
    setEditing(false)
    setEditingId(null)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!weightsValid) {
      toast.error("Competency weights must sum to 100")
      return
    }
    const payload: JobPosting = {
      job_id: editingId ?? "",
      ...form,
      required_skills: form.required_skills,
    }

    try {
      if (editing && editingId) {
        await api.updateJob(editingId, payload)
        toast.success("Job posting updated")
      } else {
        await api.createJob(payload)
        toast.success("Job posting created")
      }
      cancelForm()
      await fetchJobs()
    } catch (err: any) {
      toast.error(err.message || "Failed to save")
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await api.deleteJob(deleteTarget.job_id)
      toast.success("Job posting deleted")
      setDeleteTarget(null)
      await fetchJobs()
    } catch (err: any) {
      toast.error(err.message || "Failed to delete")
    }
  }

  function updateWeight(key: string, value: number) {
    setForm((prev) => ({
      ...prev,
      competency_weights: { ...prev.competency_weights, [key]: value },
    }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-slate-400 text-sm">Loading jobs...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Job Postings</h1>
        <p className="text-sm text-slate-500 mt-1">
          Manage interview job postings and competency weightings
        </p>
      </div>

      {showForm && (
        <Card className="rounded-xl border bg-white">
          <CardHeader>
            <CardTitle className="text-lg">
              {editing ? "Edit Job Posting" : "Create Job Posting"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSave} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="title">Title</Label>
                  <Input
                    id="title"
                    required
                    value={form.title}
                    onChange={(e) =>
                      setForm({ ...form, title: e.target.value })
                    }
                    placeholder="e.g. Senior Backend Engineer"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Department</Label>
                  <Select
                    value={form.department}
                    onValueChange={(val) => setForm({ ...form, department: val })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select department" />
                    </SelectTrigger>
                    <SelectContent>
                      {DEPARTMENTS.map((dept) => (
                        <SelectItem key={dept} value={dept}>{dept}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="description">Description</Label>
                  <textarea
                    id="description"
                    required
                    rows={8}
                    value={form.description}
                    onChange={(e) =>
                      setForm({ ...form, description: e.target.value })
                    }
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    placeholder="Job description..."
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Required Skills</Label>
                  <SkillTagInput
                    value={form.required_skills}
                    onChange={(skills) => setForm({ ...form, required_skills: skills })}
                    placeholder="Type a skill and press Enter..."
                  />
                  <p className="text-xs text-slate-400">Press Enter or comma to add a skill</p>
                </div>
                <div className="space-y-2">
                  <Label>Experience Level</Label>
                  <Select
                    value={form.experience_level}
                    onValueChange={(val) =>
                      setForm({ ...form, experience_level: val })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EXPERIENCE_LEVELS.map((level) => (
                        <SelectItem key={level} value={level}>
                          {level}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rounds">Number of Rounds</Label>
                  <Input
                    id="rounds"
                    type="number"
                    min={1}
                    max={5}
                    required
                    value={form.num_rounds}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 1
                      setForm({ ...form, num_rounds: Math.min(5, Math.max(1, val)) })
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="timeLimit">Time Limit per Question (seconds)</Label>
                  <Input
                    id="timeLimit"
                    type="number"
                    min={30}
                    max={600}
                    required
                    value={form.time_limit_seconds}
                    onChange={(e) => {
                      const val = parseInt(e.target.value) || 300
                      setForm({ ...form, time_limit_seconds: Math.min(600, Math.max(30, val)) })
                    }}
                  />
                </div>
                <div className="space-y-2 flex items-center gap-3 pt-6">
                  <Switch
                    checked={form.adaptive_difficulty}
                    onCheckedChange={(val) =>
                      setForm({ ...form, adaptive_difficulty: val })
                    }
                  />
                  <Label className="cursor-pointer">Adaptive Difficulty</Label>
                </div>
                <p className="ml-12 text-xs text-slate-400">
                  Question difficulty increases if the candidate answers well, decreases if they struggle.
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label className="text-base font-semibold">
                    Competency Weight Sliders
                  </Label>
                  <span
                    className={`text-sm font-medium ${
                      weightsValid ? "text-emerald-600" : "text-red-600"
                    }`}
                  >
                    Total: {weightSum}%
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
                  {COMPETENCY_KEYS.map((key) => (
                    <div key={key} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-sm">{COMPETENCY_LABELS[key]}</Label>
                        <span className="text-sm font-medium text-slate-700">
                          {form.competency_weights[key] ?? 0}%
                        </span>
                      </div>
                      <Slider
                        min={0}
                        max={100}
                        step={5}
                        value={[form.competency_weights[key] ?? 0]}
                        onValueChange={(val) => updateWeight(key, val[0])}
                      />
                    </div>
                  ))}
                </div>
                {!weightsValid && (
                  <p className="text-xs text-red-500">
                    Competency weights must sum to 100%. Currently at {weightSum}%.
                  </p>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                <Button type="submit" disabled={!weightsValid}>
                  Save Job Posting
                </Button>
                <Button type="button" variant="outline" onClick={cancelForm}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-xl border bg-white">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Job Postings</CardTitle>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1.5" />
            Add Job Posting
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {jobs.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No job postings"
              description="Create your first job posting to start inviting candidates."
              action={{ label: "Create Job Posting", onClick: openCreate }}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Experience Level</TableHead>
                  <TableHead>Skills</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-medium">{job.title}</TableCell>
                    <TableCell>{job.department}</TableCell>
                    <TableCell>{job.experience_level}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {job.required_skills.slice(0, 3).map((skill) => (
                          <Badge key={skill} variant="secondary" className="text-xs">
                            {skill}
                          </Badge>
                        ))}
                        {job.required_skills.length > 3 && (
                          <Badge variant="outline" className="text-xs">
                            +{job.required_skills.length - 3}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {job.created_at
                        ? new Date(job.created_at).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => openEdit(job)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50"
                          onClick={() => setDeleteTarget(job)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Job Posting</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.title}&quot;? This
              action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
