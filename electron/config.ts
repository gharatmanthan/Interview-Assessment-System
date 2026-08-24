import * as fs from 'fs';
import * as path from 'path';

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
 * Connection config lives in data/settings.json — the same file
 * app/core/settings_store.py uses — so Python and Electron agree on one
 * source of truth. It is per-machine state (which backend THIS desktop app
 * talks to), deliberately not part of the shared central database.
 */
export function getSettingsPath(): string {
  // electron/dist/config.js -> project root is two levels up.
  // In a packaged app extraResources places data/ next to the app bundle;
  // prefer resourcesPath/data when it exists, else fall back to the repo layout.
  const fromDist = path.resolve(__dirname, '..', '..');
  const packagedData = path.join(process.resourcesPath || '', 'data', 'settings.json');
  if (process.resourcesPath && fs.existsSync(packagedData)) {
    return packagedData;
  }
  return path.join(fromDist, 'data', 'settings.json');
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
