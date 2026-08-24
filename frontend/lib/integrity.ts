import { api } from './api'
import type { IntegrityFlag } from './types'

/**
 * Local-only integrity scanning bridge.
 *
 * The scan itself NEVER leaves this machine: Electron's main process probes
 * localhost ports (net.connect) and the process table natively — the same
 * checks app/candidate/integrity.py performs, reimplemented so they work
 * even in remote mode where there is no Python sidecar. Only the resulting
 * flags are uploaded to whichever backend is configured, so they land in
 * the shared Integrity Log for the recruiter.
 */

export interface LocalScanResult {
  open_ports: Array<{ port: number; tool: string }>
  flagged_processes: Array<{ pid: number; process_name: string; detail: string }>
}

export function isElectron(): boolean {
  return typeof window !== 'undefined' && !!(window as any).integrity?.runLocalScan
}

export async function runLocalScan(): Promise<LocalScanResult | null> {
  if (!isElectron()) return null
  return (window as any).integrity.runLocalScan() as Promise<LocalScanResult>
}

/** Converts a raw local scan into IntegrityFlag payloads and uploads them. */
export async function scanAndReport(sessionId: string): Promise<IntegrityFlag[]> {
  const result = await runLocalScan()
  if (!result) return []

  const flags = [
    ...result.open_ports.map(
      ({ port, tool }): Pick<IntegrityFlag, 'session_id' | 'flag_type' | 'detail' | 'severity'> => ({
        session_id: sessionId,
        flag_type: 'remote_access_port',
        detail: `${tool} port ${port} is open`,
        severity: 'high',
      })
    ),
    ...result.flagged_processes.map(
      ({ detail }): Pick<IntegrityFlag, 'session_id' | 'flag_type' | 'detail' | 'severity'> => ({
        session_id: sessionId,
        flag_type: 'suspicious_process',
        detail,
        severity: 'high',
      })
    ),
  ]

  if (flags.length > 0) {
    await api.postIntegrityFlags(flags)
  }
  return flags
}
