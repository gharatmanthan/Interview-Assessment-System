import { app, BrowserWindow } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as http from 'http';
import * as net from 'net';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.argv.includes('--dev');
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const MAX_POLL_ATTEMPTS = 30;
const POLL_INTERVAL_MS = 500;

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
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }
}

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  window.on('closed', () => {
    mainWindow = null;
    killPythonProcess();
  });

  return window;
}

app.whenReady().then(async () => {
  try {
    const port = await getFreePort();
    console.log(`Starting backend on port ${port}...`);

    pythonProcess = spawn('python', ['-m', 'api.main', '--port', String(port)], {
      cwd: PROJECT_ROOT,
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

    mainWindow = createWindow();

    if (isDev) {
      mainWindow.loadURL('http://localhost:3000');
    } else {
      mainWindow.loadFile(path.join(PROJECT_ROOT, 'frontend', 'out', 'index.html'));
    }
  } catch (err) {
    console.error('Failed to start application:', err);
    app.quit();
  }
});

app.on('will-quit', () => {
  killPythonProcess();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
