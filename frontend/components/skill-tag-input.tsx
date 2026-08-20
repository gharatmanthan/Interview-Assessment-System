"use client"

import { useState, useRef, KeyboardEvent } from "react"
import { Badge } from "@/components/ui/badge"
import { X } from "lucide-react"

interface SkillTagInputProps {
  value: string[]
  onChange: (skills: string[]) => void
  placeholder?: string
}

export function SkillTagInput({ value, onChange, placeholder = "Add a skill..." }: SkillTagInputProps) {
  const [input, setInput] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  function addSkill() {
    const trimmed = input.trim()
    if (trimmed && !value.includes(trimmed)) {
      onChange([...value, trimmed])
    }
    setInput("")
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addSkill()
    } else if (e.key === "Backspace" && input === "" && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  function removeSkill(skill: string) {
    onChange(value.filter((s) => s !== skill))
  }

  return (
    <div
      className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
      onClick={() => inputRef.current?.focus()}
    >
      {value.map((skill) => (
        <Badge key={skill} variant="secondary" className="gap-1 pr-1">
          {skill}
          <button
            type="button"
            onClick={() => removeSkill(skill)}
            className="ml-0.5 rounded-full p-0.5 hover:bg-slate-200"
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}
      <input
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={addSkill}
        placeholder={value.length === 0 ? placeholder : ""}
        className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  )
}
