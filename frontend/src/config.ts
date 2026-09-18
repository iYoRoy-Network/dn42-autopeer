/**
 * iyoroynet autopeer frontend configuration.
 */

export default {
  root: '/',
  version: '0.1.0',
  package: 'iyoroynet-autopeer/0.1.0',
  // Empty string means "same origin", which relies on the Vite dev proxy or the
  // nginx reverse proxy forwarding /api/* to the backend.
  apiPrefix: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '',
  pingIntervalMs: 180000,
  // Design credit: the layout and visual style of this frontend are inspired by
  // the iEdon-Net Auto Peering frontend (https://iedon.net), GPL-3.0.
  credit: {
    name: 'iEdon-Net Auto Peering',
    url: 'https://iedon.net',
    license: 'GPL-3.0',
  },
}
