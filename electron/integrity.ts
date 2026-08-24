import * as net from 'net';
import * as path from 'path';
import { execFile } from 'child_process';

/**
 * LOCAL-ONLY integrity scanning, native to the Electron main process.
 *
 * This is a faithful reimplementation of port_scan() / process_scan() from
 * app/candidate/integrity.py (whose functions are left untouched). It exists
 * because in remote mode there is no local Python sidecar and the central
 * server has zero visibility into this machine's network or processes.
 * Remote-access detection is only meaningful on the machine being monitored,
 * so it runs here, always, regardless of backend mode. Results are POSTed by
 * the renderer to whichever backend is configured (local sidecar or central
 * server) so they land in the shared Integrity Log.
 */

const REMOTE_ACCESS_PORTS: Record<number, string> = {
  3389: 'RDP',
  5900: 'VNC',
  5938: 'TeamViewer',
  7070: 'AnyDesk',
};

const SUSPICIOUS_PROCESSES: Record<string, string> = {
  // Remote desktop
  'teamviewer.exe': 'TeamViewer remote desktop detected',
  'anydesk.exe': 'AnyDesk remote desktop detected',
  'ammyy.exe': 'Ammyy Admin remote desktop detected',
  'splashtop.exe': 'Splashtop remote desktop detected',
  'chrome_remote_desktop.exe': 'Chrome Remote Desktop detected',
  'parseconect': 'Parallels Access detected',
  // Virtual machines
  'vmware.exe': 'VMware virtual machine detected',
  'vmware-vmx.exe': 'VMware VM process detected',
  'virtualbox.exe': 'VirtualBox detected',
  'vboxsvc.exe': 'VirtualBox service detected',
  'qemu.exe': 'QEMU virtual machine detected',
  // Screen sharing
  'vnc.exe': 'VNC screen sharing detected',
  'tightvnc.exe': 'TightVNC detected',
  'realvnc.exe': 'RealVNC detected',
  // Scripting/automation
  'autohotkey.exe': 'AutoHotkey automation detected',
  'pyautogui': 'PyAutoGUI automation detected',
};

export interface LocalScanResult {
  open_ports: Array<{ port: number; tool: string }>;
  flagged_processes: Array<{ pid: number; process_name: string; detail: string }>;
}

/** TCP connect probe against 127.0.0.1 — same approach as integrity.py. */
function probePort(port: number, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const done = (open: boolean) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
    socket.connect(port, '127.0.0.1');
  });
}

async function portScan(timeoutMs = 300): Promise<Array<{ port: number; tool: string }>> {
  const results = await Promise.all(
    Object.entries(REMOTE_ACCESS_PORTS).map(async ([portStr, tool]) => {
      const port = Number(portStr);
      const open = await probePort(port, timeoutMs);
      return open ? { port, tool } : null;
    })
  );
  return results.filter((r): r is { port: number; tool: string } => r !== null);
}

function listProcesses(): Promise<Array<{ pid: number; name: string }>> {
  return new Promise((resolve) => {
    if (process.platform === 'win32') {
      // CSV output, no header row: "name","pid",...
      execFile('tasklist', ['/FO', 'CSV', '/NH'], { windowsHide: true }, (err, stdout) => {
        if (err || !stdout) return resolve([]);
        const procs: Array<{ pid: number; name: string }> = [];
        for (const line of stdout.split('\n')) {
          const cols = line.split('","');
          if (cols.length < 2) continue;
          const name = cols[0].replace(/^"/, '').trim();
          const pid = parseInt(cols[1].replace(/"$/, '').trim(), 10);
          if (name && !Number.isNaN(pid)) procs.push({ pid, name });
        }
        resolve(procs);
      });
    } else {
      // Best-effort fallback for macOS/Linux dev machines: "  pid name"
      execFile('ps', ['-e', '-o', 'pid=,comm='], (err, stdout) => {
        if (err || !stdout) return resolve([]);
        const procs: Array<{ pid: number; name: string }> = [];
        for (const line of stdout.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const spaceIdx = trimmed.indexOf(' ');
          if (spaceIdx === -1) continue;
          const pid = parseInt(trimmed.slice(0, spaceIdx), 10);
          const full = trimmed.slice(spaceIdx + 1).trim();
          if (!Number.isNaN(pid) && full) procs.push({ pid, name: path.basename(full) });
        }
        resolve(procs);
      });
    }
  });
}

async function processScan(): Promise<Array<{ pid: number; process_name: string; detail: string }>> {
  const procs = await listProcesses();
  const findings: Array<{ pid: number; process_name: string; detail: string }> = [];
  for (const proc of procs) {
    const nameLower = proc.name.toLowerCase();
    for (const [pattern, detail] of Object.entries(SUSPICIOUS_PROCESSES)) {
      if (nameLower.includes(pattern)) {
        findings.push({ pid: proc.pid, process_name: proc.name, detail });
        break;
      }
    }
  }
  return findings;
}

export async function runLocalScan(): Promise<LocalScanResult> {
  const [open_ports, flagged_processes] = await Promise.all([portScan(), processScan()]);
  return { open_ports, flagged_processes };
}
