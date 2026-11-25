// Argus Earth: camera points from public/vision/latest.json (contract/README.md), coloured by vehicle count.
// Plain points layer for the Week 1 milestone; per-feature layers (density, weather...) replace it later.
import { createLocalGeoJsonLayer } from '../../data/localGeojsonCore.js';

const LATEST_URL = '/vision/latest.json';

// Tunable thresholds: vehicles seen in one still frame (a snapshot, not flow).
const colorFor = ({ total }) =>
  total == null ? '#9aa0a6' : total < 5 ? '#34c759' : total < 15 ? '#ffb020' : '#ff453a';

async function loadFeatures({ signal }) {
  const response = await fetch(LATEST_URL, { cache: 'no-store', signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const doc = await response.json();
  return doc.cameras.map((c) => {
    const d = c.density;
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
      properties: {
        name: c.camera_id,
        total: d ? d.total : null,
        __gevDetails: [
          d ? `${d.total} vehicles (${d.car} car, ${d.truck} truck, ${d.bus} bus)` : 'not analysed yet',
          `${c.frame_time}${c.is_night ? ' (night)' : ''}`,
        ],
      },
    };
  });
}

export function createVisionCamerasLayer(services) {
  return createLocalGeoJsonLayer(
    {
      id: 'vision-cameras',
      name: 'Vision Cameras',
      color: '#00d4ff',
      icon: '◉',
      source: 'Argus Earth',
      loadFeatures,
      featureColor: colorFor,
    },
    services,
  );
}
