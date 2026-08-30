import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as http from 'http';
import * as net from 'net';
import * as fs from 'fs';
import { loadConfig, needsSetup, saveConfig, AppConfig } from './config';
import { runLocalScan } from './integrity';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;
let frontendServer: http.Server | null = null;
let startInFlight = false;

const isDev = process.argv.includes('--dev');
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const STATIC_ROOT = path.join(PROJECT_ROOT, 'frontend', 'out');
const MAX_POLL_ATTEMPTS = 30;
const POLL_INTERVAL_MS = 500;

/**
 * In a packaged app (extraResources) the Python sidecar lives under
 * process.resourcesPath (api/, app/, data/) rather than the repo layout
 * PROJECT_ROOT used in dev. Returning the resources dir here lets us point
 * cwd/PYTHONPATH and the static root at real, unpacked locations on disk.
 * In dev/from-source we fall back to the repository root.
 */
function packagedRoot(): string {
  return process.resourcesPath || PROJECT_ROOT;
}

/**
 * True when the process is running from a packaged electron-builder bundle.
 * extraResources files are placed under resources/, not the repo layout.
 */
function isPackaged(): boolean {
  return !!(process.resourcesPath
    && fs.existsSync(path.join(process.resourcesPath, 'api', 'main.py')));
}

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
        reject(new Error(`Server on port ${port} did not start within ${MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000}s`));
        return;
      }
      const req = http.get(`http://localhost:${port}/health`, (res: http.IncomingMessage) => {
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

function killPythonProcess(): void {
  if (pythonProcess && !pythonProcess.killed) {
    // SIGTERM is unreliable on Windows; taskkill /T takes the whole child tree.
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(pythonProcess.pid), '/T', '/F'], { windowsHide: true });
    } else {
      pythonProcess.kill('SIGTERM');
    }
    pythonProcess = null;
  }
}

/**
 * Serve the exported (static) Next.js build over loopback HTTP.
 *
 * `loadFile(index.html)` breaks client-side routing — deep links like /jobs
 * or /reports fail because there is no server to apply the SPA fallback. This
 * serves ./frontend/out on a random 127.0.0.1 port with a MIME map and an
 * index.html fallback for anything that is not a real static asset, plus a
 * canonical `<base>`-independent location for fetch() relative to origin.
 */
function serveFrontend(): Promise<string> {
  return new Promise((resolve, reject) => {
    const root = path.resolve(STATIC_ROOT);
    const server = http.createServer((req, res) => {
      try {
        if (!req.url) {
          res.writeHead(400).end('Bad Request');
          return;
        }
        const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const rel = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
        // Keep any request inside the exported build — no escaping via ../
        const filePath = path.resolve(root, rel);
        if (filePath !== root && !filePath.startsWith(root + path.sep)) {
          res.writeHead(403).end('Forbidden');
          return;
        }
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
          const data = fs.readFileSync(filePath);
          res.writeHead(200, {
            'Content-Type': MIME_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
          });
          res.end(data);
          return;
        }
        // SPA fallback: unknown paths are client-side routes.
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
 * Where should the frontend send shared-data requests?
 *
 * - local mode: the FastAPI sidecar spawned below, on a random loopback port
 *   (unchanged behavior — single-machine / on-site use)
 * - remote mode: no sidecar; everything goes to the central deployed server.
 *   Integrity scans still run LOCALLY via integrity.ts and their results are
 *   POSTed to this same base URL by the renderer.
 */
async function resolveApiBaseUrl(config: AppConfig): Promise<{ baseUrl: string; spawnedPort: number | null }> {
  if (config.backendMode === 'remote') {
    let url = config.remoteApiUrl.replace(/\/+$/, '');
    if (!/^https?:\/\//.test(url)) url = `https://${url}`;
    return { baseUrl: url, spawnedPort: null };
  }

  const port = await getFreePort();
  console.log(`Starting backend on port ${port}...`);

  // In a packaged app the Python source is unpacked under resourcesPath (via
  // extraResources). Point cwd + PYTHONPATH there so `python -m api.main`
  // resolves api/ and app/ — app.asar is virtual and cannot be cwd.
  const backendRoot = isPackaged() ? process.resourcesPath! : PROJECT_ROOT;

  pythonProcess = spawn('python', ['-m', 'api.main', '--port', String(port)], {
    cwd: backendRoot,
    env: {
      ...process.env,
      PYTHONPATH: backendRoot,
      INTERVIEWIQ_PACKAGED: isPackaged() ? '1' : '0',
    },
    stdio: 'inherit',
  });

  pythonProcess.on('error', (err: Error) => {
    console.error('Failed to start Python process:', err);
  });

  pythonProcess.on('exit', (code: number | null) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });

  await waitForServer(port);
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
      // The renderer cannot read Node state directly (contextIsolation), so
      // the resolved API base URL travels in through preload's process.argv.
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
  // Called after the setup screen / settings page changes backendMode or
  // remoteApiUrl: the injected API base URL lives in preload's argv, so a
  // fresh window (and sidecar decision) is required to apply it.
  ipcMain.handle('app:restart-window', async () => {
    killPythonProcess();
    await startApp();
  });
}

async function startApp(): Promise<void> {
  // Guard against concurrent starts (whenReady + activate + restart-window can
  // fire close together) which would otherwise spawn multiple Python sidecars
  // and leak static servers on top of each other.
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

// Prevent a second app instance from spawning its own Python sidecar and
// fighting over the same settings/data files.
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
