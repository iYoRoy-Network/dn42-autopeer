import { computed, reactive, ref } from 'vue'
import { api, setDevAsn, DN42_AUTOPEER_ASN_MAX, DN42_AUTOPEER_ASN_MIN } from './common/packetHandler'
import type {
  JobRecord,
  NodeSummary,
  PeerPayload,
  PeerResponse,
  PeerStatus,
  Principal,
  Session,
} from './common/packetHandler'

export interface PeerForm {
  mode: 'create' | 'edit'
  node: string
  // Bound to a-input-number, which emits null when the field is cleared rather
  // than the empty string this field would otherwise hold.
  asn: string | null
  contact: string
  publicKey: string
  endpoint: string
  // Bound to a-input-number, which emits null once the field is cleared.
  mtu: number | null
  mpBgp: boolean
  ipv4Enabled: boolean
  ipv6Enabled: boolean
  ipv6Mode: 'link_local' | 'global'
  ipv4Address: string
  ipv6Address: string
  ipv6LinkLocalAddress: string
}

const currentUser = ref<Principal | null>(null)
const nodes = ref<NodeSummary[]>([])
const sessions = ref<Session[]>([])
const statuses = ref<PeerStatus[]>([])
const loading = ref(false)
const loadingStatus = ref(false)
const error = ref('')
const notice = ref('')
const pendingJob = ref<JobRecord | null>(null)
const saving = ref(false)
const activeSession = ref<Session | null>(null)
const wizardStep = ref(1)
const form = reactive<PeerForm>({
  mode: 'create',
  node: '',
  asn: '',
  contact: '',
  publicKey: '',
  endpoint: '',
  mtu: 1420,
  mpBgp: false,
  ipv4Enabled: true,
  ipv6Enabled: true,
  ipv6Mode: 'link_local',
  ipv4Address: '',
  ipv6Address: '',
  ipv6LinkLocalAddress: '',
})

let pollTimer: number | null = null

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const statusByPeer = computed(() => new Map(statuses.value.map((s) => [`${s.node}:${s.asn}`, s])))
const statusForSession = (session: Session): PeerStatus | undefined =>
  statusByPeer.value.get(`${session.node.id}:${session.peer.asn}`)

const sessionCount = computed(() => sessions.value.length)
const onlineSessionCount = computed(
  () => sessions.value.filter((s) => statusForSession(s)?.bgp?.up).length,
)
const totalReceived = computed(() =>
  sessions.value.reduce((n, s) => n + Number(statusForSession(s)?.wireguard?.rx_bytes || 0), 0),
)
const totalTransmitted = computed(() =>
  sessions.value.reduce((n, s) => n + Number(statusForSession(s)?.wireguard?.tx_bytes || 0), 0),
)
const totalImportedRoutes = computed(() =>
  sessions.value.reduce((n, s) => n + Number(statusForSession(s)?.bgp?.routes_imported || 0), 0),
)
const totalExportedRoutes = computed(() =>
  sessions.value.reduce((n, s) => n + Number(statusForSession(s)?.bgp?.routes_exported || 0), 0),
)

function sessionsForNode(nodeId: string): Session[] {
  return sessions.value.filter((s) => s.node.id === nodeId)
}

function resetForm(session: Session | null = null, node: NodeSummary | null = null): void {
  const peer = session?.peer
  form.mode = peer ? 'edit' : 'create'
  form.node = session?.node.id ?? node?.id ?? ''
  // Login already proves ASN ownership, so default to the signed-in ASN for
  // every role. Administrators keep the field editable to create a session on
  // behalf of an ASN that did not come through the web UI.
  form.asn = peer ? String(peer.asn) : String(currentUser.value?.asn ?? '')
  form.contact = peer?.description ?? ''
  form.publicKey = peer?.wireguard_public_key ?? ''
  form.endpoint = peer?.wireguard_endpoint ?? ''
  form.mtu = peer?.mtu ?? 1420
  const bgp = (peer?.bgp ?? {}) as Record<string, unknown>
  form.mpBgp = Boolean(bgp.mp_bgp ?? peer?.extended_next_hop)
  form.ipv4Enabled = Boolean(bgp.ipv4_enabled ?? peer?.address_families?.includes('ipv4') ?? true)
  form.ipv6Enabled = Boolean(bgp.ipv6_enabled ?? peer?.address_families?.includes('ipv6') ?? true)
  form.ipv6Mode = (bgp.ipv6_mode as 'link_local' | 'global') ??
    (peer?.bgp_transport?.mode === 'ipv6' ? 'global' : 'link_local')
  form.ipv4Address = (bgp.ipv4_address as string) ??
    (peer?.bgp_transport?.mode === 'ipv4' ? peer.bgp_transport.remote_address : '') ?? ''
  form.ipv6Address = (bgp.ipv6_address as string) ??
    (peer?.bgp_transport?.mode === 'ipv6' ? peer.bgp_transport.remote_address : '') ?? ''
  form.ipv6LinkLocalAddress = (bgp.ipv6_link_local_address as string) ??
    (peer?.bgp_transport?.mode === 'ipv6_link_local' ? peer.bgp_transport.remote_address : '') ?? ''
  wizardStep.value = 1
}

// Mirrors canonical_endpoint() in src/autopeer/domain/peer.py: host:port, or
// [ipv6]:port for IPv6 literals. The backend rejects anything else with a 422.
function isEndpoint(value: string): boolean {
  const text = value.trim()
  if (!text) return false
  let host: string
  let port: string
  if (text.startsWith('[')) {
    const closing = text.indexOf(']')
    if (closing <= 1 || text[closing + 1] !== ':') return false
    host = text.slice(1, closing)
    port = text.slice(closing + 2)
  } else {
    const parts = text.split(':')
    if (parts.length !== 2) return false
    ;[host, port] = parts
  }
  if (!host || !/^\d+$/.test(port)) return false
  const portNumber = Number(port)
  return portNumber >= 1 && portNumber <= 65535
}

// Deliberately validates address *shape* only. Python's ipaddress.is_global()
// is a blocklist over IANA's special-purpose registry rather than a 2000::/3
// allowlist, so mirroring it in JS risks false rejections. The backend stays
// authoritative on global-unicast policy and now names the field when it 422s.
function isIPv6Literal(value: string): boolean {
  const text = value.trim()
  if (!/^[0-9a-fA-F:]+$/.test(text)) return false
  const compression = text.indexOf('::')
  if (compression !== text.lastIndexOf('::')) return false // "::" may appear once
  if (compression === -1) {
    const groups = text.split(':')
    return groups.length === 8 && groups.every((g) => /^[0-9a-fA-F]{1,4}$/.test(g))
  }
  const head = text.slice(0, compression)
  const tail = text.slice(compression + 2)
  const headGroups = head ? head.split(':') : []
  const tailGroups = tail ? tail.split(':') : []
  if (![...headGroups, ...tailGroups].every((g) => /^[0-9a-fA-F]{1,4}$/.test(g))) return false
  return headGroups.length + tailGroups.length < 8
}

// fe80::/10 is the IPv6 link-local range, i.e. first hextet 0xfe80..0xfebf.
function isLinkLocalV6(value: string): boolean {
  const first = parseInt(value.trim().toLowerCase().split(':')[0] || '0', 16)
  return first >= 0xfe80 && first <= 0xfebf
}

function ipKind(value: string): 'v4' | 'v6' | 'v6-link-local' | 'invalid' {
  const text = value.trim()
  if (!text) return 'invalid'
  if (text.includes(':')) {
    if (!isIPv6Literal(text)) return 'invalid'
    return isLinkLocalV6(text) ? 'v6-link-local' : 'v6'
  }
  const parts = text.split('.')
  if (parts.length !== 4) return 'invalid'
  if (!parts.every((part) => /^\d+$/.test(part) && Number(part) <= 255)) return 'invalid'
  return 'v4'
}

function validate(step: number): string | null {
  if (step === 1 && !form.contact.trim()) return 'Contact information is required.'
  if (step === 1 && isAdmin.value && form.mode === 'create') {
    if (!formAsn()) return 'Peer ASN is required.'
    const asn = Number(formAsn())
    if (asn < DN42_AUTOPEER_ASN_MIN || asn > DN42_AUTOPEER_ASN_MAX)
      return `Peer ASN must be within ${DN42_AUTOPEER_ASN_MIN}..${DN42_AUTOPEER_ASN_MAX}.`
  }
  if (step === 2 && (!form.publicKey.trim() || !form.endpoint.trim()))
    return 'WireGuard connection details are required.'
  if (step === 2 && !isEndpoint(form.endpoint))
    return 'The WireGuard endpoint must be a host and port, for example peer.example:22024.'
  if (step === 2 && !form.mpBgp && !form.ipv4Enabled && !form.ipv6Enabled)
    return 'Enable IPv4, IPv6, or MP-BGP.'
  if (step === 2 && form.ipv4Enabled && !form.mpBgp && ipKind(form.ipv4Address) !== 'v4')
    return 'An IPv4 address is required.'
  if (step === 2 && form.ipv6Enabled && form.ipv6Mode === 'global' && !['v6', 'v6-link-local'].includes(ipKind(form.ipv6Address)))
    return 'An IPv6 address is required.'
  if (step === 2 && form.ipv6Enabled && form.ipv6Mode === 'link_local' && ipKind(form.ipv6LinkLocalAddress) !== 'v6-link-local')
    return 'An IPv6 link-local address (fe80::/10) is required.'
  return null
}

function nextWizardStep(): boolean {
  const message = validate(wizardStep.value)
  if (message) {
    error.value = message
    return false
  }
  error.value = ''
  if (wizardStep.value < 3) wizardStep.value += 1
  return true
}

function previousWizardStep(): void {
  if (wizardStep.value > 1) wizardStep.value -= 1
}

function setMpBgp(enabled: boolean): void {
  form.mpBgp = enabled
  if (enabled) {
    form.ipv4Enabled = false
    form.ipv6Enabled = true
  }
}

function remoteAddressForForm(): string {
  if (form.mpBgp || (form.ipv6Enabled && !form.ipv4Enabled)) {
    return form.ipv6Mode === 'global' ? form.ipv6Address : form.ipv6LinkLocalAddress
  }
  return form.ipv4Address
}

function sessionModelLabel(): string {
  if (form.mpBgp) return form.ipv6Mode === 'global' ? 'IPv6 Global + MP-BGP + ENH' : 'IPv6 Link-Local + MP-BGP + ENH'
  if (form.ipv4Enabled && form.ipv6Enabled)
    return form.ipv6Mode === 'global' ? 'IPv6 Global + independent sessions' : 'IPv6 Link-Local + independent sessions'
  if (form.ipv4Enabled) return 'IPv4 only'
  return form.ipv6Mode === 'global' ? 'IPv6 Global only' : 'IPv6 Link-Local only'
}

function asRequestPayload(): PeerPayload {
  // Number(null) is 0, which the backend rejects as mtu < 576. Fall back to the
  // same default the form starts with when the field was cleared.
  const mtu = Number(form.mtu)
  return {
    contact: form.contact,
    wireguard: {
      public_key: form.publicKey,
      endpoint: form.endpoint,
      mtu: Number.isFinite(mtu) && mtu >= 576 && mtu <= 9000 ? mtu : 1420,
    },
    bgp: {
      mp_bgp: form.mpBgp,
      ipv4_enabled: form.ipv4Enabled,
      ipv6_enabled: form.ipv6Enabled,
      ipv6_mode: form.ipv6Mode,
      ipv4_address: form.ipv4Address || null,
      ipv6_address: form.ipv6Address || null,
      ipv6_link_local_address: form.ipv6LinkLocalAddress || null,
    },
  }
}

async function loadSessions(): Promise<void> {
  if (!currentUser.value) {
    sessions.value = []
    return
  }
  const listPeers = isAdmin.value ? api.adminPeers : api.peers
  const results = await Promise.all(
    nodes.value.map(async (node) => {
      try {
        const peers = await listPeers(node.id)
        return peers.map((peer) => ({ node, peer }))
      } catch {
        return []
      }
    }),
  )
  sessions.value = results.flat()
}

async function loadStatus(): Promise<void> {
  if (!currentUser.value) return
  loadingStatus.value = true
  try {
    statuses.value = isAdmin.value ? await api.adminAllStatus() : await api.status()
  } catch (requestError) {
    statuses.value = []
    notice.value = (requestError as Error).message
  } finally {
    loadingStatus.value = false
  }
}

async function bootstrap(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    currentUser.value = await api.currentUser()
    nodes.value = isAdmin.value ? await api.adminNodes() : await api.nodes()
    await loadSessions()
    await loadStatus()
  } catch (requestError) {
    const err = requestError as { status?: number; message?: string }
    if (err.status === 401) {
      currentUser.value = null
      nodes.value = []
      sessions.value = []
      statuses.value = []
    } else {
      error.value = err.message ?? 'Failed to load.'
    }
  } finally {
    loading.value = false
  }
}

function watchJob(job: JobRecord): void {
  pendingJob.value = job
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    try {
      const latest = await api.job(job.id)
      pendingJob.value = latest
      if (latest.status !== 'succeeded' && latest.status !== 'failed') return
      if (pollTimer) clearInterval(pollTimer)
      pollTimer = null
      if (latest.status === 'succeeded') {
        notice.value = `Job ${latest.id} completed.`
        await loadSessions()
        await loadStatus()
      } else {
        error.value = latest.error || `Job ${latest.id} failed.`
      }
    } catch (requestError) {
      if (pollTimer) clearInterval(pollTimer)
      pollTimer = null
      error.value = (requestError as Error).message
    }
  }, 1500)
}

// a-input-number hands back a number (or null once cleared) even though the form
// models the field as a string, so normalise before treating it as text.
function formAsn(): string {
  return String(form.asn ?? '').trim()
}

async function saveSession(): Promise<boolean> {
  if (!form.node) {
    error.value = 'No node is selected for this session. Reopen the wizard from a node.'
    return false
  }
  const message = validate(1) || validate(2)
  if (message) {
    error.value = message
    return false
  }
  if (isAdmin.value && form.mode === 'create' && !formAsn()) {
    error.value = 'Peer ASN is required for an administrator-created session.'
    return false
  }
  saving.value = true
  error.value = ''
  try {
    const payload = asRequestPayload()
    const asn = Number(formAsn())
    const job =
      form.mode === 'create'
        ? isAdmin.value
          ? await api.createAdminPeer(form.node, asn, payload)
          : await api.createPeer(form.node, payload)
        : isAdmin.value
          ? await api.patchAdminPeer(form.node, asn, payload)
          : await api.patchPeer(form.node, asn, payload)
    notice.value = `Queued ${job.kind.replaceAll('_', ' ')} for AS${formAsn() || currentUser.value?.asn}.`
    watchJob(job)
    return true
  } catch (requestError) {
    error.value = (requestError as Error).message
    return false
  } finally {
    saving.value = false
  }
}

async function deleteSession(session: Session): Promise<boolean> {
  saving.value = true
  error.value = ''
  try {
    const { node, peer } = session
    const job = isAdmin.value
      ? await api.deleteAdminPeer(node.id, peer.asn)
      : await api.deletePeer(node.id, peer.asn)
    notice.value = `Queued removal for AS${peer.asn} on ${node.id}.`
    watchJob(job)
    return true
  } catch (requestError) {
    error.value = (requestError as Error).message
    return false
  } finally {
    saving.value = false
  }
}

async function logout(): Promise<void> {
  try {
    await api.logout()
  } finally {
    localStorage.removeItem('autopeer-dev-asn')
    setDevAsn('')
    currentUser.value = null
    sessions.value = []
    statuses.value = []
  }
}

async function applyDevIdentity(asn: string): Promise<void> {
  localStorage.setItem('autopeer-dev-asn', asn)
  setDevAsn(asn)
  await bootstrap()
}

function openCreate(node: NodeSummary): void {
  resetForm(null, node)
}

function openEdit(session: Session): void {
  activeSession.value = session
  resetForm(session)
}

function clearError(): void {
  error.value = ''
}

function clearNotice(): void {
  notice.value = ''
}

export function useAutopeer() {
  return {
    currentUser,
    nodes,
    sessions,
    statuses,
    loading,
    loadingStatus,
    error,
    notice,
    pendingJob,
    saving,
    activeSession,
    wizardStep,
    form,
    isAdmin,
    sessionCount,
    onlineSessionCount,
    totalReceived,
    totalTransmitted,
    totalImportedRoutes,
    totalExportedRoutes,
    statusForSession,
    sessionsForNode,
    bootstrap,
    loadStatus,
    loadSessions,
    openCreate,
    openEdit,
    resetForm,
    setMpBgp,
    nextWizardStep,
    previousWizardStep,
    saveSession,
    deleteSession,
    remoteAddressForForm,
    sessionModelLabel,
    clearError,
    clearNotice,
    logout,
    applyDevIdentity,
  }
}

setDevAsn(localStorage.getItem('autopeer-dev-asn') || '')
