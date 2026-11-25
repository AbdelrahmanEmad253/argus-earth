import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import { resolveAllowedHosts } from '../../build/allowedHosts.js';
import { createBrowserViteConfig } from '../../build/vite.js';
import { localProviderPlugins } from '../providers/local.js';
import { localMcpPlugin } from '../mcp/plugin.js';
import { apiNotFoundPlugin } from './api-not-found.js';
import { conformanceReferencesPlugin } from './conformance-references.js';
import { googleTokenUnavailablePlugin } from './google-token-unavailable.js';
import { standaloneVoiceTools } from './voiceTools.js';
import { unwatchedRuntimeDirsPlugin } from './unwatched-cache.js';

const root = fileURLToPath(new URL('../../', import.meta.url));

/** Load this checkout's configuration and attach its local provider middleware. */
export function standaloneConfig(
  { command, mode },
  { nominatimStorageDir } = {},
) {
  const loaded = loadEnv(mode, root, '');
  for (const [key, value] of Object.entries(loaded)) {
    if (process.env[key] === undefined) process.env[key] = value;
  }
  const tools = standaloneVoiceTools();
  return createBrowserViteConfig({
    plugins: [
      ...localProviderPlugins({
        realtime: { tools },
        gemini: { tools },
        nominatimStorageDir,
      }),
      localMcpPlugin(),
      // Argus Earth: same-origin path to the local Python API (the browser CSP blocks other ports).
      {
        name: 'argus-api-proxy',
        config: () => ({
          server: {
            proxy: {
              '/argus': {
                target: 'http://127.0.0.1:8000',
                rewrite: (p) => p.replace(/^\/argus/, ''),
              },
            },
          },
        }),
      },
      googleTokenUnavailablePlugin(),
      conformanceReferencesPlugin(),
      apiNotFoundPlugin(),
      unwatchedRuntimeDirsPlugin(),
    ],
    googleApiKey: process.env.GOOGLE_MAPS_API_KEY,
    cesiumToken: process.env.CESIUM_ION_TOKEN,
    photonUrl: process.env.PHOTON_URL,
    mapillaryToken: process.env.MAPILLARY_CLIENT_TOKEN,
    host: process.env.HOST,
    port: process.env.PORT,
    allowedHosts: resolveAllowedHosts(process.env.GEV_ALLOWED_HOSTS),
    command,
  });
}

export default defineConfig(standaloneConfig);
