import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as http from 'http';
import * as net from 'net';
import * as fs from 'fs';
import { loadConfig, needsSetup, saveConfig, AppConfig, getUserDataDir, getWhisperModelDir } from './config';
import { runLocalScan } from './integrity';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;
let frontendServer: http.Server | null = null;
let startInFlight = false;

const isDev = process.argv.includes('--dev');

// ---------------------------------------------------------------------------
// Path resolution — NEVER assume cwd. Two explicit layouts:
//
//   DEVELOPMENT (from-source, `npm run dev`):
//     <repo>/
//       electron/
//       api/
//       app/
//       frontend/out/
//       data/                 (writable dev data)
//
//   PACKAGED (electron-builder extraResources -> process.resourcesPath):
//     <InstallDir>/resources/
//       python/               (portable CPython + site-packages)
//       backend/
//         api/
//         app/
//       whisper/faster-whisper-base/
//       frontend/out/
//     AND app.getPath('userData')           (writable per-user data)
// ---------------------------------------------------------------------------

function resourcesRoot(): string {
  return process.resourcesPath || '';
}

/**
 * True when running from a packaged Electron bundle (NSIS/portable install).
 *
 * NOTE: gate on `app.isPackaged` — NEVER on `process.resourcesPath` alone.
 * When running *unpackaged* from source (`electron .`), Electron still sets
 * process.resourcesPath to `node_modules/electron/dist/resources`, so trusting
 * mere truthiness would try to find python/backend under Electron's own runtime
 * and fail with ENOENT. `app.isPackaged` is the reliable dev-vs-packaged flag.
 */
function isPackagedApp(): boolean {
  return !!app.isPackaged;
}

function backendRoot(): string {
  // Packaged: resources/backend (has api/ + app/). Dev: repo root.
  if (isPackagedApp()) {
    return path.join(process.resourcesPath, 'backend');
  }
  return path.resolve(__dirname, '..', '..');
}

function staticRoot(): string {
  if (isPackagedApp()) {
    return path.join(process.resourcesPath, 'frontend', 'out');
  }
  return path.resolve(__dirname, '..', '..', 'frontend', 'out');
}

function pythonExecutable(): string {
  // Packaged: resources/python/python.exe (self-contained). Dev: `python`
  // from PATH (the developer's environment).
  if (isPackagedApp()) {
    return path.join(process.resourcesPath, 'python', 'python.exe');
  }
  return 'python';
}

/** True when running from a packaged bundle (resources present). */
function isPackaged(): boolean {
  return isPackagedApp()
    && fs.existsSync(path.join(process.resourcesPath, 'backend', 'api', 'main.py'));
}

const MAX_POLL_ATTEMPTS = 60;
const POLL_INTERVAL_MS = 500;

const MIME_TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.map': 'application/json',
};

function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, () => {
      const address = server.address();
      if (address && typeof address === 'object') {
        const port = address.port;
        server.close(() => resolve(port));
      } else {
        server.close(() => reject(new Error('Failed to get free port')));
      }
    });
    server.on('error', reject);
  });
}

function waitForServer(port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const poll = () => {
      attempts++;
      if (attempts > MAX_POLL_ATTEMPTS) {
        reject(new Error(`Backend on port ${port} did not become ready within ${MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000}s`));
        return;
      }
      const req = http.get(`http://127.0.0.1:${port}/health`, (res: http.IncomingMessage) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          setTimeout(poll, POLL_INTERVAL_MS);
        }
      });
      req.on('error', () => setTimeout(poll, POLL_INTERVAL_MS));
      req.end();
    };
    poll();
  });
}

function showStartupError(message: string): void {
  dialog.showErrorBox('InterviewIQ could not start', message);
  console.error('Startup error:', message);
}

function killPythonProcess(): void {
  if (pythonProcess && !pythonProcess.killed && pythonProcess.pid) {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(pythonProcess.pid), '/T', '/F'], { windowsHide: true });
    } else {
      pythonProcess.kill('SIGTERM');
    }
    pythonProcess = null;
  }
}

/**
 * Serve the exported (static) Next.js build over loopback HTTP with SPA
 * fallback. All requests are contained within the static root (no `..`)
 * so the renderer can deep-link /jobs, /reports, etc.
 */
function serveFrontend(): Promise<string> {
  return new Promise((resolve, reject) => {
    const root = path.resolve(staticRoot());
    const server = http.createServer((req, res) => {
      try {
        if (!req.url) {
          res.writeHead(400).end('Bad Request');
          return;
        }
        const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const rel = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
        const filePath = path.resolve(root, rel);

        // Try exact match, then .html, then /index.html for static export compatibility
        const candidates = [
          filePath,
          filePath + '.html',
          path.join(filePath, 'index.html'),
        ];

        let served = false;
        for (const candidate of candidates) {
          if (candidate !== root && !candidate.startsWith(root + path.sep)) {
            continue;
          }
          if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
            const data = fs.readFileSync(candidate);
            res.writeHead(200, {
              'Content-Type': MIME_TYPES[path.extname(candidate).toLowerCase()] || 'application/octet-stream',
            });
            res.end(data);
            served = true;
            break;
          }
        }
        if (served) return;

        const index = path.join(root, 'index.html');
        if (fs.existsSync(index)) {
          res.writeHead(200, { 'Content-Type': MIME_TYPES['.html'] });
          res.end(fs.readFileSync(index));
          return;
        }
        res.writeHead(404).end('Not Found');
      } catch {
        res.writeHead(500).end('Internal Server Error');
      }
    });

    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (address && typeof address === 'object') {
        frontendServer = server;
        resolve(`http://127.0.0.1:${address.port}`);
      } else {
        server.close();
        reject(new Error('Failed to start frontend static server'));
      }
    });
  });
}

/**
 * Spawn the FastAPI sidecar on a dynamic loopback port using the bundled
 * Python runtime (packaged) or the developer's `python` (dev). Binds only to
 * 127.0.0.1. Waits for /health before returning so the UI never loads a dead
 * backend.
 */
async function spawnBackend(port: number): Promise<void> {
  const python = pythonExecutable();
  const root = backendRoot();
  const dataDir = getUserDataDir();
  const whisperDir = getWhisperModelDir();

  // Ensure the writable data dir exists before Python touches it.
  fs.mkdirSync(dataDir, { recursive: true });

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PYTHONPATH: root,
    PYTHONUTF8: '1',
    INTERVIEWIQ_DATA_DIR: dataDir,
  };
  if (whisperDir) env['INTERVIEWIQ_WHISPER_MODEL_DIR'] = whisperDir;

  console.log(`Starting Python backend: ${python}  port=${port}  cwd=${root}`);

  // Use explicit pipes — NOT 'inherit'.
  // In a packaged Windows GUI subsystem app, the parent has no console.
  // stdio: 'inherit' gives the child (console-subsystem Python) invalid
  // handles and it silently creates a hidden console, making every startup
  // error invisible and preventing Electron from detecting /health.
  pythonProcess = spawn(python, ['-m', 'api.main', '--port', String(port)], {
    cwd: root,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout?.on('data', (d: Buffer) => {
    const line = d.toString().trimEnd();
    console.log(`[python:stdout] ${line}`);
  });
  pythonProcess.stderr?.on('data', (d: Buffer) => {
    const line = d.toString().trimEnd();
    console.error(`[python:stderr] ${line}`);
  });

  pythonProcess.on('error', (err: Error) => {
    console.error('Failed to start Python sidecar:', err);
    showStartupError(
      `The bundled Python backend failed to start.\n\n${err.message}\n\n` +
      `This usually means the InterviewIQ installation is incomplete. ` +
      `Please reinstall the application.`,
    );
  });

  pythonProcess.on('exit', (code: number | null) => {
    console.log(`Python sidecar exited with code ${code}`);
    pythonProcess = null;
  });

  try {
    await waitForServer(port);
  } catch (err) {
    showStartupError(
      `The InterviewIQ backend did not become ready in time.\n\n${(err as Error).message}\n\n` +
      (isPackaged()
        ? 'The installed application appears to be damaged. Please reinstall InterviewIQ.'
        : 'For development, start the backend manually (python -m api.main) and try again.'),
    );
    throw err;
  }
}

async function resolveApiBaseUrl(config: AppConfig): Promise<{ baseUrl: string; spawnedPort: number | null }> {
  if (config.backendMode === 'remote') {
    let url = config.remoteApiUrl.replace(/\/+$/, '');
    if (!/^https?:\/\//.test(url)) url = `https://${url}`;
    return { baseUrl: url, spawnedPort: null };
  }

  const port = await getFreePort();
  console.log(`Starting local backend on 127.0.0.1:${port} ...`);
  await spawnBackend(port);
  console.log('Backend is ready');
  return { baseUrl: `http://127.0.0.1:${port}`, spawnedPort: port };
}

function createWindow(baseUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--interviewiq-api-url=${baseUrl}`],
    },
  });

  window.on('closed', () => {
    mainWindow = null;
    killPythonProcess();
  });

  return window;
}

function registerIpc(): void {
  ipcMain.handle('app:get-config', () => {
    const current = loadConfig();
    return { ...current, needsSetup: needsSetup(current) };
  });
  ipcMain.handle('app:set-config', (_event, update: Partial<AppConfig>) => {
    const next = saveConfig(update);
    return { ...next, needsSetup: needsSetup(next) };
  });
  ipcMain.handle('integrity:local-scan', () => runLocalScan());
  ipcMain.handle('app:restart-window', async () => {
    killPythonProcess();
    await startApp();
  });
}

async function startApp(): Promise<void> {
  if (startInFlight) {
    return;
  }
  startInFlight = true;
  try {
    const config = loadConfig();
    console.log(`Backend mode: ${config.backendMode}${config.remoteApiUrl ? ` (${config.remoteApiUrl})` : ''}`);

    const { baseUrl } = await resolveApiBaseUrl(config);

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.destroy();
      mainWindow = null;
    }

    mainWindow = createWindow(baseUrl);

    if (isDev) {
      mainWindow.loadURL('http://localhost:3000');
    } else {
      const frontendUrl = await serveFrontend();
      mainWindow.loadURL(frontendUrl);
    }
  } catch (err) {
    console.error('Failed to start application:', err);
    app.quit();
  } finally {
    startInFlight = false;
  }
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    registerIpc();
    startApp();
  });
}

app.on('will-quit', () => {
  killPythonProcess();
  if (frontendServer) {
    frontendServer.close();
    frontendServer = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    startApp();
  }
});
