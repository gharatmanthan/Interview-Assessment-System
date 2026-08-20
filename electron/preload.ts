import { contextBridge, desktopCapturer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getSources: () => desktopCapturer.getSources({ types: ['window', 'screen'] }),
  platform: process.platform,
});
