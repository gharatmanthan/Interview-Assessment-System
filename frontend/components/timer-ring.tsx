"use client"

interface TimerRingProps {
  seconds: number
  maxSeconds: number
  size?: number
}

export function TimerRing({ seconds, maxSeconds, size = 120 }: TimerRingProps) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const progress = maxSeconds > 0 ? seconds / maxSeconds : 0
  const offset = circumference - progress * circumference

  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const display = `${mins}:${secs.toString().padStart(2, "0")}`

  const colorVar = progress > 0.75 ? "var(--destructive)" : progress > 0.5 ? "var(--warning)" : "var(--primary)"

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={6}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colorVar}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 linear"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-2xl font-semibold tabular-nums text-foreground">{display}</span>
        <span className="text-xs leading-relaxed text-muted-foreground">remaining</span>
      </div>
    </div>
  )
}
