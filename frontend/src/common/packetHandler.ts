import config from '@/config'

let developmentAsn = ''

export function setDevAsn(asn: string): void {
  developmentAsn = asn
}

export class ApiError extends Error {
  status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  if (developmentAsn) headers['X-Autopeer-ASN'] = developmentAsn

  const response = await fetch(`${config.apiPrefix}${path}`, {
    credentials: 'include',
    ...options,
    headers,
  })

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    throw new ApiError(body?.detail ?? `Request failed with HTTP ${response.status}`, response.status)
  }
  return body as T
}

// --- Domain types (mirror the backend Pydantic models) ---

export type PrincipalRole = 'admin' | 'user'

export interface Principal {
  asn: number
  role: PrincipalRole
  display_name: string | null
}

export interface NodeRuntimeMetrics {
  rx_bytes?: number | null
  tx_bytes?: number | null
  rx_bytes_per_second?: number | null
  tx_bytes_per_second?: number | null
  collected_at?: number | null
}

export interface NodePeeringMetadata {
  display_name?: string | null
  subtitle?: string | null
  protocol_stack?: 'ipv4' | 'ipv6' | 'dual_stack'
  endpoint?: string | null
  agent_url?: string | null
  publickey?: string | null
  listen_port_policy?: Record<string, unknown>
  exporters?: Record<string, string>
}

export interface NodeSummary {
  id: string
  name: string
  peering_enabled: boolean
  peer_count: number
  online_peer_count?: number | null
  runtime_metrics?: NodeRuntimeMetrics | null
  peering?: NodePeeringMetadata
}

export interface BgpTransport {
  mode: 'ipv6_link_local' | 'ipv4' | 'ipv6'
  remote_address: string
}

export interface PeerConnectionInfo {
  wireguard_endpoint?: string | null
  public_key?: string | null
  listen_port: number
  bgp_transport: BgpTransport['mode']
  bgp_local_address: string
}

export interface PeerResponse {
  node: string
  asn: number
  description: string | null
  wireguard_public_key: string
  wireguard_endpoint: string | null
  listen_port: number
  mtu: number
  bgp_transport: BgpTransport
  address_families: ('ipv4' | 'ipv6')[]
  extended_next_hop: boolean
  session_mode?: string | null
  bgp: Record<string, unknown>
  connection_info?: PeerConnectionInfo | null
  managed_schema: string
}

export interface WireGuardSummary {
  rx_bytes?: number
  tx_bytes?: number
  latest_handshake_age_seconds?: number
  latest_handshake_seconds?: number
  present?: boolean
  [key: string]: unknown
}

export interface BgpSummary {
  up?: boolean
  routes_imported?: number
  routes_exported?: number
  [key: string]: unknown
}

export interface PeerStatus {
  node: string
  asn: number
  interface: string
  protocol: string
  wireguard: WireGuardSummary
  bgp: BgpSummary
  node_metrics: Record<string, unknown>
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'validating'
  | 'committing'
  | 'applying'
  | 'succeeded'
  | 'failed'

export interface JobRecord {
  id: string
  kind: string
  status: JobStatus
  requested_by_asn: number
  node?: string | null
  peer_asn?: number | null
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error?: string | null
  created_at: string
  updated_at: string
}

export interface Session {
  node: NodeSummary
  peer: PeerResponse
}

// --- Peer create / patch payloads ---

export interface WireGuardPayload {
  public_key: string
  endpoint: string
  mtu: number
}

export interface BgpPayload {
  mp_bgp: boolean
  ipv4_enabled: boolean
  ipv6_enabled: boolean
  ipv6_mode: 'link_local' | 'global'
  ipv4_address: string | null
  ipv6_address: string | null
  ipv6_link_local_address: string | null
}

export interface PeerPayload {
  contact: string
  wireguard: WireGuardPayload
  bgp: BgpPayload
}

// --- API surface ---

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  currentUser: () => request<Principal>('/api/v1/me'),
  nodes: () => request<NodeSummary[]>('/api/v1/nodes'),
  adminNodes: () => request<NodeSummary[]>('/api/v1/admin/nodes'),

  peers: (node: string) => request<PeerResponse[]>(`/api/v1/nodes/${encodeURIComponent(node)}/peers`),
  getPeer: (node: string, asn: number | string) =>
    request<PeerResponse>(`/api/v1/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`),
  adminPeers: (node: string) =>
    request<PeerResponse[]>(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers`),
  adminPeer: (node: string, asn: number | string) =>
    request<PeerResponse>(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`),

  status: () => request<PeerStatus[]>('/api/v1/me/peers/status'),
  adminStatus: (asn: number | string) =>
    request<PeerStatus[]>(`/api/v1/admin/peers/${encodeURIComponent(asn)}/status`),
  adminAllStatus: () => request<PeerStatus[]>('/api/v1/admin/peers/status'),

  job: (jobId: string) => request<JobRecord>(`/api/v1/jobs/${encodeURIComponent(jobId)}`),

  createPeer: (node: string, payload: PeerPayload) =>
    request<JobRecord>(`/api/v1/nodes/${encodeURIComponent(node)}/peers`, json(payload)),
  createAdminPeer: (node: string, asn: number | string, payload: PeerPayload) =>
    request<JobRecord>(
      `/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`,
      json(payload),
    ),
  patchPeer: (node: string, asn: number | string, payload: PeerPayload) =>
    request<JobRecord>(
      `/api/v1/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`,
      { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    ),
  patchAdminPeer: (node: string, asn: number | string, payload: PeerPayload) =>
    request<JobRecord>(
      `/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`,
      { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    ),
  deletePeer: (node: string, asn: number | string) =>
    request<JobRecord>(`/api/v1/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`, { method: 'DELETE' }),
  deleteAdminPeer: (node: string, asn: number | string) =>
    request<JobRecord>(`/api/v1/admin/nodes/${encodeURIComponent(node)}/peers/${encodeURIComponent(asn)}`, { method: 'DELETE' }),

  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
}
