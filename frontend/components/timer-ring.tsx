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

  const color = progress > 0.75 ? "#EF4444" : progress > 0.5 ? "#F59E0B" : "#5B5FEF"

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#E5E7EB"
          strokeWidth={6}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 linear"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-2xl font-semibold tabular-nums text-slate-900">{display}</span>
        <span className="text-xs text-slate-500">remaining</span>
      </div>
    </div>
  )
}
