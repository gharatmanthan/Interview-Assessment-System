import * as fs from 'fs';
import * as path from 'path';
import { app } from 'electron';

export type BackendMode = 'local' | 'remote';

export interface AppConfig {
  backendMode: BackendMode;
  remoteApiUrl: string;
}

/**
 * Default server address offered on the first-run setup screen.
 *
 * Bake your deployed central server URL in at build/package time:
 *   set INTERVIEWIQ_DEFAULT_REMOTE_URL before `npm run build`
 * so most candidates never have to edit anything by hand.
 */
export const DEFAULT_REMOTE_URL = process.env.INTERVIEWIQ_DEFAULT_REMOTE_URL || '';

/**
 * The ONE authoritative, per-user, writable data directory.
 *
 *  * Packaged: Electron's userData dir (%APPDATA%/InterviewIQ on Windows).
 *    This is where app.db, recordings, uploads, resumes, live_frames,
 *    face_profiles, models AND settings.json live. Never inside
 *    process.resourcesPath (read-only/install dir).
 *  * Dev: the repository's `data/` directory (repo layout).
 *
 * Python reads this same location via the INTERVIEWIQ_DATA_DIR env var set
 * by main.ts when spawning the sidecar, so Electron and Python always agree
 * on one data root — never two databases.
 */
export function getUserDataDir(): string {
  if (app && app.isPackaged) {
    return app.getPath('userData');
  }
  // Dev: repo data/ dir (two levels up from electron/dist).
  return path.resolve(__dirname, '..', '..', 'data');
}

export function getSettingsPath(): string {
  return path.join(getUserDataDir(), 'settings.json');
}

/**
 * Directory containing the bundled Whisper model, or null in dev.
 * Packaged: <resources>/whisper/faster-whisper-base
 * Dev: null -> faster-whisper uses its default (HuggingFace) cache.
 */
export function getWhisperModelDir(): string | null {
  if (app && app.isPackaged && process.resourcesPath) {
    return path.join(process.resourcesPath, 'whisper', 'faster-whisper-base');
  }
  return null;
}

function readSettingsFile(): Record<string, unknown> {
  try {
    return JSON.parse(fs.readFileSync(getSettingsPath(), 'utf-8'));
  } catch {
    return {};
  }
}

export function loadConfig(): AppConfig {
  const settings = readSettingsFile();
  const mode: BackendMode = settings['backend_mode'] === 'remote' ? 'remote' : 'local';
  let url = typeof settings['remote_api_url'] === 'string' ? (settings['remote_api_url'] as string).trim() : '';
  if (!url) url = DEFAULT_REMOTE_URL;
  return { backendMode: mode, remoteApiUrl: url };
}

/** True when remote mode is selected but no server address has been saved yet. */
export function needsSetup(config: AppConfig): boolean {
  return config.backendMode === 'remote' && !config.remoteApiUrl;
}

export function saveConfig(update: Partial<AppConfig>): AppConfig {
  const settingsPath = getSettingsPath();
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });

  let current: Record<string, unknown> = {};
  try {
    current = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
  } catch {
    current = {};
  }

  if (update.backendMode !== undefined) current['backend_mode'] = update.backendMode;
  if (update.remoteApiUrl !== undefined) current['remote_api_url'] = update.remoteApiUrl;

  fs.writeFileSync(settingsPath, JSON.stringify(current, null, 2));
  return loadConfig();
}
