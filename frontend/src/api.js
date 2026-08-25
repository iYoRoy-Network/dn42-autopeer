const baseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

let developmentAsn = ''

export function setDevAsn(asn) {
  developmentAsn = asn
}

async function request(path, options = {}) {
  const headers = {
    Accept: 'application/json',
    ...options.headers,
  }
  if (developmentAsn) {
    headers['X-Autopeer-ASN'] = developmentAsn
  }

  const response = await fetch(`${baseUrl}${path}`, {
    credentials: 'include',
    ...options,
    headers,
  })

  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    const error = new Error(body?.detail ?? `Request failed with HTTP ${response.status}`)
    error.status = response.status
    throw error
  }
  return body
}

export const api = {
  currentUser: () => request('/api/v1/me'),
  nodes: () => request('/api/v1/nodes'),
  adminNodes: () => request('/api/v1/admin/nodes'),
  peers: (node) => request(`/api/v1/nodes/${encodeURIComponent(node)}/peers`),
  adminPeers: (node) => request(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers`),
  status: () => request('/api/v1/me/peers/status'),
  job: (jobId) => request(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
  createPeer: (node, payload) =>
    request(`/api/v1/nodes/${encodeURIComponent(node)}/peers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  createAdminPeer: (node, asn, payload) =>
    request(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${asn}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  patchPeer: (node, asn, payload) =>
    request(`/api/v1/nodes/${encodeURIComponent(node)}/peers/${asn}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  patchAdminPeer: (node, asn, payload) =>
    request(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${asn}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deletePeer: (node, asn) =>
    request(`/api/v1/nodes/${encodeURIComponent(node)}/peers/${asn}`, { method: 'DELETE' }),
  deleteAdminPeer: (node, asn) =>
    request(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${asn}`, { method: 'DELETE' }),
  logout: () => request('/api/v1/auth/logout', { method: 'POST' }),
}
