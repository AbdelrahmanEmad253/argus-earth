// Argus Earth: search camera frames by description (typed or spoken). Talks to the local Python API through
// the /argus proxy; the Groq key never reaches the browser. Scene-level search only: no person search.
import { createLocalGeoJsonLayer } from '../../data/localGeojsonCore.js';

const API = '/argus';
let features = [];
let viewer = null;
let layer = null;
let panel = null;

const toFeatures = (results) =>
  results.map((r) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
    properties: {
      name: r.name || r.camera_id,
      __gevDetails: [`score ${r.score}`, r.frame_time],
    },
  }));

async function show(results, status, ui) {
  features = toFeatures(results);
  await layer.replaceFeatures(viewer, features);
  ui.status.textContent = status;
  ui.list.replaceChildren(
    ...results.map((r) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:8px;margin:6px 0;align-items:center';
      if (r.image_url) {
        const img = document.createElement('img');
        img.src = API + r.image_url;
        img.style.cssText = 'width:96px;height:72px;object-fit:cover;border-radius:4px';
        row.append(img);
      }
      const txt = document.createElement('div');
      txt.textContent = `${r.name || r.camera_id} · ${r.score} · ${r.frame_time}`;
      txt.style.fontSize = '12px';
      row.append(txt);
      return row;
    }),
  );
}

async function typedSearch(q, ui) {
  ui.status.textContent = 'Searching…';
  const res = await fetch(`${API}/search?q=${encodeURIComponent(q)}&limit=10`);
  const body = await res.json();
  if (!res.ok) return void (ui.status.textContent = body.detail || 'Search failed');
  await show(body.results, `${body.results.length} closest matches`, ui);
}

async function voiceSearch(text, ui) {
  ui.status.textContent = `Heard: ${text}`;
  const res = await fetch(`${API}/agent`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  const body = await res.json();
  if (!res.ok) return void (ui.status.textContent = 'Voice search failed');
  await show(body.search ? body.search.results : [], body.reply, ui);
  if (body.reply) speechSynthesis.speak(new SpeechSynthesisUtterance(body.reply));
}

function buildPanel() {
  const el = document.createElement('div');
  el.style.cssText =
    'position:fixed;left:16px;bottom:16px;width:340px;max-height:60vh;overflow:auto;z-index:50;' +
    'padding:10px;background:rgba(8,16,28,.92);color:#cfe;border:1px solid #0cf;border-radius:8px;font:13px sans-serif';
  const input = document.createElement('input');
  input.placeholder = 'Describe a scene: snowy road, fog, heavy traffic';
  input.style.cssText = 'width:100%;box-sizing:border-box;padding:6px;margin-bottom:6px';
  const status = document.createElement('div');
  status.style.cssText = 'font-size:12px;margin:4px 0';
  const list = document.createElement('div');
  const ui = { status, list };
  const run = () => input.value.trim() && typedSearch(input.value.trim(), ui).catch(() => (status.textContent = 'API offline'));
  const btn = document.createElement('button');
  btn.textContent = 'Search';
  btn.onclick = run;
  el.append(input, btn);
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Rec) {
    // Chrome/Edge send the audio to their cloud speech service; typed search needs none of that.
    const mic = document.createElement('button');
    mic.textContent = '🎤';
    mic.style.marginLeft = '6px';
    mic.onclick = () => {
      const r = new Rec();
      r.lang = 'en-US';
      r.interimResults = false;
      r.onresult = (e) => voiceSearch(e.results[0][0].transcript, ui).catch(() => (status.textContent = 'API offline'));
      r.onerror = () => (status.textContent = 'Microphone unavailable');
      r.start();
    };
    el.append(mic);
  }
  el.append(status, list);
  // The fork has global keyboard shortcuts; keep typing inside the panel.
  for (const t of ['keydown', 'keyup', 'keypress']) el.addEventListener(t, (e) => e.stopPropagation());
  input.addEventListener('keydown', (e) => e.key === 'Enter' && run());
  return el;
}

export function createVisionSearchLayer(services) {
  layer = createLocalGeoJsonLayer(
    {
      id: 'vision-search',
      name: 'Vision Search',
      color: '#ff4fd8',
      icon: '⌕',
      source: 'Argus Earth',
      loadFeatures: async () => features,
    },
    services,
  );
  const { enable, disable } = layer;
  return {
    ...layer,
    enable: async (v) => {
      viewer = v;
      panel ??= buildPanel();
      document.body.append(panel);
      return enable(v);
    },
    disable: (v) => {
      panel?.remove();
      return disable(v);
    },
  };
}
