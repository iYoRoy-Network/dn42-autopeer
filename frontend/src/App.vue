<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, setDevAsn } from './api'

const storedDevAsn = localStorage.getItem('autopeer-dev-asn') ?? ''
const devAsn = ref(storedDevAsn)
const activePage = ref('nodes')
const currentUser = ref(null)
const nodes = ref([])
const sessions = ref([])
const statuses = ref([])
const loading = ref(true)
const loadingStatus = ref(false)
const error = ref('')
const notice = ref('')
const dialogOpen = ref(false)
const deleteOpen = ref(false)
const saving = ref(false)
const pendingJob = ref(null)
const activeSession = ref(null)
const pollTimer = ref(null)

const form = reactive({
  mode: 'create',
  node: '',
  asn: '',
  contact: '',
  publicKey: '',
  endpoint: '',
  mtu: 1420,
  transportMode: 'ipv6_link_local',
  remoteAddress: '',
  extendedNextHop: true,
})
const wizardStep = ref(1)

setDevAsn(storedDevAsn)

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const statusByNode = computed(() => new Map(statuses.value.map((status) => [status.node, status])))
const sessionCount = computed(() => sessions.value.length)
const onlineSessionCount = computed(
  () => sessions.value.filter((session) => statusForSession(session)?.bgp?.up).length,
)
const totalReceived = computed(() =>
  sessions.value.reduce(
    (total, session) => total + Number(statusForSession(session)?.wireguard?.rx_bytes || 0),
    0,
  ),
)
const totalTransmitted = computed(() =>
  sessions.value.reduce(
    (total, session) => total + Number(statusForSession(session)?.wireguard?.tx_bytes || 0),
    0,
  ),
)
const totalImportedRoutes = computed(() =>
  sessions.value.reduce(
    (total, session) => total + Number(statusForSession(session)?.bgp?.routes_imported || 0),
    0,
  ),
)
const totalExportedRoutes = computed(() =>
  sessions.value.reduce(
    (total, session) => total + Number(statusForSession(session)?.bgp?.routes_exported || 0),
    0,
  ),
)
const totalNodeReceived = (node) => node.runtime_metrics?.rx_bytes
const totalNodeTransmitted = (node) => node.runtime_metrics?.tx_bytes
const currentNodeReceiveRate = (node) => node.runtime_metrics?.rx_bytes_per_second
const currentNodeTransmitRate = (node) => node.runtime_metrics?.tx_bytes_per_second
function formatRate(value) {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) return '—'
  return `${formatBytes(value)}/s`
}
function sessionsForNode(nodeId) {
  return sessions.value.filter((session) => session.node.id === nodeId)
}

function statusForSession(session) {
  if (!currentUser.value || Number(session.peer.asn) !== Number(currentUser.value.asn)) return null
  return statusByNode.value.get(session.node.id) ?? null
}

function formatBytes(value) {
  if (value === undefined || value === null) return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let unit = 0
  let result = numeric
  while (Math.abs(result) >= 1024 && unit < units.length - 1) {
    result /= 1024
    unit += 1
  }
  return `${result.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[unit]}`
}

function formatEpoch(value) {
  if (!value) return '—'
  const milliseconds = Number(value) * 1000
  if (!Number.isFinite(milliseconds)) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(milliseconds),
  )
}

function formatHandshake(status) {
  const age = status?.wireguard?.latest_handshake_age_seconds
  if (age !== undefined && age !== null) {
    const numeric = Number(age)
    if (!Number.isFinite(numeric)) return '—'
    if (numeric < 60) return `${Math.round(numeric)} seconds ago`
    if (numeric < 3600) return `${Math.round(numeric / 60)} minutes ago`
    if (numeric < 86400) return `${Math.round(numeric / 3600)} hours ago`
    return `${Math.round(numeric / 86400)} days ago`
  }
  return formatEpoch(status?.wireguard?.latest_handshake_seconds)
}

function resetForm(session = null, node = null) {
  const peer = session?.peer
  form.mode = peer ? 'edit' : 'create'
  form.node = session?.node.id ?? node?.id ?? ''
  form.asn = peer ? String(peer.asn) : String(isAdmin.value ? '' : (currentUser.value?.asn ?? ''))
  form.contact = peer?.description ?? ''
  form.publicKey = peer?.wireguard_public_key ?? ''
  form.endpoint = peer?.wireguard_endpoint ?? ''
  form.mtu = peer?.mtu ?? 1420
  form.transportMode = peer?.bgp_transport?.mode ?? 'ipv6_link_local'
  form.remoteAddress = peer?.bgp_transport?.remote_address ?? ''
  form.extendedNextHop = peer?.extended_next_hop ?? true
  wizardStep.value = 1
}

async function loadSessions() {
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
      } catch (requestError) {
        // A single inaccessible or temporarily unavailable node must not hide sessions elsewhere.
        return []
      }
    }),
  )
  sessions.value = results.flat()
}

async function loadStatus() {
  if (!currentUser.value) return
  loadingStatus.value = true
  try {
    statuses.value = await api.status()
  } catch (requestError) {
    // Exporters are optional. Configuration views remain available without them.
    notice.value = requestError.message
    statuses.value = []
  } finally {
    loadingStatus.value = false
  }
}

async function bootstrap() {
  loading.value = true
  error.value = ''
  try {
    currentUser.value = await api.currentUser()
    nodes.value = isAdmin.value ? await api.adminNodes() : await api.nodes()
    await Promise.all([loadSessions(), loadStatus()])
  } catch (requestError) {
    if (requestError.status === 401) {
      currentUser.value = null
      nodes.value = []
      sessions.value = []
      statuses.value = []
    } else {
      error.value = requestError.message
    }
  } finally {
    loading.value = false
  }
}

function openCreate(node) {
  resetForm(null, node)
  dialogOpen.value = true
}

function openEdit(session) {
  activeSession.value = session
  resetForm(session)
  dialogOpen.value = true
}

function openSessionDetails(session) {
  activeSession.value = session
  activePage.value = 'session-detail'
}

function backToSessions() {
  activePage.value = 'sessions'
  activeSession.value = null
}

function nextWizardStep() {
  if (wizardStep.value === 1 && !form.contact.trim()) {
    error.value = 'Contact information is required.'
    return
  }
  if (wizardStep.value === 2 && (!form.publicKey.trim() || !form.endpoint.trim() || !form.remoteAddress.trim())) {
    error.value = 'WireGuard and BGP connection details are required.'
    return
  }
  error.value = ''
  if (wizardStep.value < 3) wizardStep.value += 1
}

function previousWizardStep() {
  if (wizardStep.value > 1) wizardStep.value -= 1
}

function asRequestPayload() {
  const wireguard = {
    public_key: form.publicKey,
    endpoint: form.endpoint,
    mtu: Number(form.mtu),
  }
  const bgp = {
    transport: {
      mode: form.transportMode,
      remote_address: form.remoteAddress,
    },
    extended_next_hop: form.extendedNextHop,
  }
  if (form.mode === 'create') {
    return {
      contact: form.contact,
      wireguard,
      bgp: { ...bgp, address_families: ['ipv4', 'ipv6'] },
    }
  }
  return { contact: form.contact, wireguard, bgp }
}

function watchJob(job) {
  pendingJob.value = job
  clearInterval(pollTimer.value)
  pollTimer.value = window.setInterval(async () => {
    try {
      const latest = await api.job(job.id)
      pendingJob.value = latest
      if (!['succeeded', 'failed'].includes(latest.status)) return
      clearInterval(pollTimer.value)
      pollTimer.value = null
      if (latest.status === 'succeeded') {
        notice.value = `Job ${latest.id} completed.`
        await Promise.all([loadSessions(), loadStatus()])
      } else {
        error.value = latest.error || `Job ${latest.id} failed.`
      }
    } catch (requestError) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
      error.value = requestError.message
    }
  }, 1500)
}

async function saveSession() {
  if (!form.node) return
  if (!form.contact.trim()) {
    error.value = 'Contact information is required.'
    wizardStep.value = 1
    return
  }
  if (!form.publicKey.trim() || !form.endpoint.trim() || !form.remoteAddress.trim()) {
    error.value = 'WireGuard and BGP connection details are required.'
    wizardStep.value = 2
    return
  }
  if (isAdmin.value && form.mode === 'create' && !form.asn.trim()) {
    error.value = 'Peer ASN is required for an administrator-created session.'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const payload = asRequestPayload()
    const job = form.mode === 'create'
      ? (isAdmin.value
        ? await api.createAdminPeer(form.node, Number(form.asn), payload)
        : await api.createPeer(form.node, payload))
      : (isAdmin.value
        ? await api.patchAdminPeer(form.node, Number(form.asn), payload)
        : await api.patchPeer(form.node, Number(form.asn), payload))
    dialogOpen.value = false
    notice.value = `Queued ${job.kind.replace('_', ' ')} for AS${form.asn}.`
    watchJob(job)
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

async function deleteSession() {
  if (!activeSession.value) return
  saving.value = true
  error.value = ''
  try {
    const { node, peer } = activeSession.value
    const job = isAdmin.value
      ? await api.deleteAdminPeer(node.id, peer.asn)
      : await api.deletePeer(node.id, peer.asn)
    deleteOpen.value = false
    notice.value = `Queued removal for AS${peer.asn} on ${node.id}.`
    watchJob(job)
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

async function applyDevIdentity() {
  localStorage.setItem('autopeer-dev-asn', devAsn.value.trim())
  setDevAsn(devAsn.value.trim())
  await bootstrap()
}

async function logout() {
  try {
    await api.logout()
  } finally {
    localStorage.removeItem('autopeer-dev-asn')
    setDevAsn('')
    devAsn.value = ''
    currentUser.value = null
    sessions.value = []
    statuses.value = []
  }
}

function kioubitReturnUrl() {
  return `${window.location.origin}/api/v1/auth/callback`
}

onMounted(bootstrap)
onUnmounted(() => clearInterval(pollTimer.value))
</script>

<template>
  <main class="app-shell">
    <template v-if="loading">
      <section class="loading-screen" aria-live="polite">
        <mdui-circular-progress aria-label="Loading autopeer" />
        <p>Loading autopeer control plane…</p>
      </section>
    </template>

    <template v-else-if="!currentUser">
      <section class="login-shell" aria-labelledby="login-title">
        <div class="brand-lockup">
          <div class="brand-mark" aria-hidden="true">↔</div>
          <div>
            <p class="eyebrow">DN42 CONTROL PLANE</p>
            <h1 id="login-title">iyoroynet autopeer</h1>
            <p>Manage your WireGuard and BGP peer sessions from one control plane.</p>
          </div>
        </div>

        <mdui-card class="login-card" variant="outlined">
          <h2>Sign in</h2>
          <p>Use Kioubit to verify your ASN and open a signed local session.</p>
          <kioubit-auth-btn :return="kioubitReturnUrl()" token="" />
          <mdui-divider class="login-divider" />
          <p class="muted">Development only: send a local ASN header through the frontend proxy.</p>
          <mdui-text-field
            label="Development ASN"
            type="number"
            :value="devAsn"
            @input="devAsn = $event.target.value"
          />
          <mdui-button variant="text" full-width @click="applyDevIdentity">Use development identity</mdui-button>
        </mdui-card>
      </section>
    </template>

    <template v-else>
      <header class="app-header">
        <a class="wordmark" href="#" @click.prevent="activePage = 'nodes'">
          <span class="wordmark-mark">↔</span>
          <span>iyoroynet <b>autopeer</b></span>
        </a>
        <div class="identity" aria-label="Current identity">
          <div class="identity-avatar">{{ currentUser.display_name?.slice(0, 1) ?? 'A' }}</div>
          <div>
            <strong>{{ currentUser.display_name || `AS${currentUser.asn}` }}</strong>
            <span>AS{{ currentUser.asn }} · {{ currentUser.role }}</span>
          </div>
          <mdui-button variant="text" @click="logout">Sign out</mdui-button>
        </div>
      </header>

      <section class="workspace">
        <nav class="page-tabs" aria-label="Primary sections">
          <button :class="{ active: activePage === 'nodes' }" type="button" @click="activePage = 'nodes'">
            All nodes <span>{{ nodes.length }}</span>
          </button>
          <button :class="{ active: activePage === 'sessions' }" type="button" @click="activePage = 'sessions'">
            My sessions <span>{{ sessionCount }}</span>
          </button>
        </nav>

        <div v-if="error" class="message message-error" role="alert">
          <span>{{ error }}</span>
          <mdui-button variant="text" @click="error = ''">Dismiss</mdui-button>
        </div>
        <div v-if="notice" class="message message-info" role="status">
          <span>{{ notice }}</span>
          <mdui-button variant="text" @click="notice = ''">Dismiss</mdui-button>
        </div>

        <section v-if="pendingJob" class="job-banner" aria-live="polite">
          <div>
            <span class="job-dot" :class="`job-${pendingJob.status}`" aria-hidden="true" />
            <strong>{{ pendingJob.kind.replace('_', ' ') }}</strong>
            <span>· {{ pendingJob.status }}</span>
          </div>
          <code>{{ pendingJob.id }}</code>
        </section>

        <template v-if="activePage === 'nodes'">
          <section class="page-heading">
            <div>
              <p class="eyebrow">AVAILABLE LOCATIONS</p>
              <h1>All nodes</h1>
              <p>Choose a node to create a new peer session or manage your sessions on that node.</p>
            </div>
          </section>

          <section class="node-grid">
            <mdui-card v-for="node in nodes" :key="node.id" class="node-card compact-node" variant="outlined">
              <div class="node-summary">
                <div>
                  <p class="eyebrow">{{ node.id }}</p>
                  <h2>{{ node.peering.display_name || node.name }}</h2>
                  <p class="node-subtitle">{{ node.peering.subtitle || 'DN42 WireGuard peering' }}</p>
                </div>
                <span class="stack-pill">
                  {{ node.peering.protocol_stack === 'ipv4' ? 'IPv4 only' : node.peering.protocol_stack === 'ipv6' ? 'IPv6 only' : 'Dual stack' }}
                </span>
              </div>
              <div class="node-metrics">
                <div><span>Peers</span><strong>{{ node.peer_count }} total · {{ node.online_peer_count ?? '—' }} online</strong></div>
                <div><span>Traffic</span><strong>↓ {{ formatBytes(totalNodeReceived(node)) }} · ↑ {{ formatBytes(totalNodeTransmitted(node)) }}</strong></div>
                <div><span>Current bandwidth</span><strong>↓ {{ formatRate(currentNodeReceiveRate(node)) }} · ↑ {{ formatRate(currentNodeTransmitRate(node)) }}</strong></div>
              </div>
              <div class="node-actions">
                <mdui-button
                  v-if="sessionsForNode(node.id).length"
                  variant="outlined"
                  @click="openSessionDetails(sessionsForNode(node.id)[0])"
                >
                  View peering
                </mdui-button>
                <mdui-button v-else variant="filled" :disabled="!node.peering_enabled" @click="openCreate(node)">
                  Start peering
                </mdui-button>
              </div>
            </mdui-card>
          </section>
        </template>

        <template v-else-if="activePage === 'sessions'">
          <section class="page-heading sessions-heading">
            <div>
              <p class="eyebrow">YOUR PEERINGS</p>
              <h1>My sessions <span class="heading-count">{{ sessionCount }}</span></h1>
              <p>Live health and useful routing data for your WireGuard and BGP sessions.</p>
            </div>
            <div class="heading-actions">
              <mdui-button variant="outlined" :loading="loadingStatus" @click="loadStatus">Refresh status</mdui-button>
              <mdui-button variant="filled" @click="activePage = 'nodes'">Add peering</mdui-button>
            </div>
          </section>

          <section v-if="sessions.length" class="session-dashboard">
            <div class="summary-grid">
              <article class="summary-card"><span>Health</span><strong>{{ onlineSessionCount }}/{{ sessionCount }}</strong><small>BGP sessions online</small></article>
              <article class="summary-card"><span>Issues</span><strong>{{ sessionCount - onlineSessionCount }}</strong><small>sessions need attention</small></article>
              <article class="summary-card"><span>Routes</span><strong>{{ totalImportedRoutes + totalExportedRoutes }}</strong><small>{{ totalImportedRoutes }} imported · {{ totalExportedRoutes }} exported</small></article>
              <article class="summary-card"><span>Received</span><strong>{{ formatBytes(totalReceived) }}</strong><small>WireGuard total</small></article>
              <article class="summary-card"><span>Transmitted</span><strong>{{ formatBytes(totalTransmitted) }}</strong><small>WireGuard total</small></article>
            </div>

            <div class="peering-rows">
              <article v-for="session in sessions" :key="`${session.node.id}-${session.peer.asn}`" class="peering-row">
                <div class="peering-node">
                  <span class="node-avatar">{{ (session.node.peering.display_name || session.node.name).slice(0, 2).toUpperCase() }}</span>
                  <div>
                    <strong>{{ session.node.peering.display_name || session.node.name }}</strong>
                    <span>{{ session.node.peering.subtitle || session.node.id }}</span>
                  </div>
                </div>
                <div class="peering-state">
                  <strong :class="statusForSession(session)?.bgp?.up ? 'state-good' : 'state-unknown'">
                    <span class="state-dot" />{{ statusForSession(session)?.bgp?.up ? 'Established' : 'Status unavailable' }}
                  </strong>
                  <span>{{ session.peer.bgp_transport.mode.replaceAll('_', ' ') }} · {{ session.peer.address_families.join(' + ') }}</span>
                </div>
                <div class="peering-data">
                  <span>↓ {{ formatBytes(statusForSession(session)?.wireguard?.rx_bytes) }}</span>
                  <span>↑ {{ formatBytes(statusForSession(session)?.wireguard?.tx_bytes) }}</span>
                </div>
                <div class="session-actions">
                  <mdui-button variant="outlined" @click="openSessionDetails(session)">Details</mdui-button>
                  <mdui-button variant="text" @click="activeSession = session; deleteOpen = true">Delete</mdui-button>
                </div>
              </article>
            </div>
          </section>

          <section v-else class="empty-state compact-empty">
            <div class="empty-icon" aria-hidden="true">+</div>
            <h2>No peer sessions yet</h2>
            <p>Choose an available node to create your first WireGuard and BGP session.</p>
            <mdui-button variant="filled" @click="activePage = 'nodes'">Browse nodes</mdui-button>
          </section>
        </template>

        <template v-else-if="activePage === 'session-detail' && activeSession">
          <section class="detail-toolbar">
            <mdui-button variant="text" @click="backToSessions">← Back to sessions</mdui-button>
            <div class="session-actions">
              <mdui-button variant="outlined" @click="openEdit(activeSession)">Edit</mdui-button>
              <mdui-button variant="text" @click="deleteOpen = true">Delete</mdui-button>
            </div>
          </section>
          <section class="detail-heading">
            <p class="eyebrow">{{ activeSession.node.id }} · AS{{ activeSession.peer.asn }}</p>
            <h1>{{ activeSession.node.peering.display_name || activeSession.node.name }}</h1>
            <p>{{ activeSession.node.peering.subtitle || 'DN42 WireGuard peering session' }}</p>
          </section>
          <section class="detail-grid">
            <article class="detail-panel">
              <h2>Peer configuration</h2>
              <dl class="details-grid">
                <div><dt>Contact</dt><dd>{{ activeSession.peer.description }}</dd></div>
                <div><dt>WireGuard interface</dt><dd class="monospace">dn42_{{ activeSession.peer.asn }}</dd></div>
                <div><dt>Peer endpoint · Your input</dt><dd class="monospace">{{ activeSession.peer.wireguard_endpoint }}</dd></div>
                <div><dt>Peer public key · Your input</dt><dd class="monospace">{{ activeSession.peer.wireguard_public_key }}</dd></div>
                <div><dt>Link MTU</dt><dd>{{ activeSession.peer.mtu }}</dd></div>
                <div><dt>BGP transport</dt><dd>{{ activeSession.peer.bgp_transport.mode.replaceAll('_', ' ') }}</dd></div>
                <div><dt>Remote BGP address</dt><dd class="monospace">{{ activeSession.peer.bgp_transport.remote_address }}</dd></div>
              </dl>
            </article>
            <article class="detail-panel">
              <h2>Our connection information · Provided by this node</h2>
              <dl class="details-grid one-column">
                <div><dt>WireGuard endpoint</dt><dd class="monospace">{{ activeSession.peer.connection_info?.wireguard_endpoint || 'Not configured' }}</dd></div>
                <div><dt>WireGuard public key</dt><dd class="monospace">{{ activeSession.peer.connection_info?.public_key || 'Not configured' }}</dd></div>
                <div><dt>BGP local address</dt><dd class="monospace">{{ activeSession.peer.connection_info?.bgp_local_address }}</dd></div>
              </dl>
            </article>
          </section>
          <section v-if="statusForSession(activeSession)" class="detail-metrics">
            <article><span>BGP status</span><strong>{{ statusForSession(activeSession).bgp.up ? 'Established' : 'Unavailable' }}</strong></article>
            <article><span>Imported routes</span><strong>{{ statusForSession(activeSession).bgp.routes_imported ?? '—' }}</strong></article>
            <article><span>Exported routes</span><strong>{{ statusForSession(activeSession).bgp.routes_exported ?? '—' }}</strong></article>
            <article><span>Received</span><strong>{{ formatBytes(statusForSession(activeSession).wireguard.rx_bytes) }}</strong></article>
            <article><span>Transmitted</span><strong>{{ formatBytes(statusForSession(activeSession).wireguard.tx_bytes) }}</strong></article>
            <article><span>Last handshake</span><strong>{{ formatHandshake(statusForSession(activeSession)) }}</strong></article>
          </section>
        </template>
      </section>

      <mdui-dialog :open="dialogOpen" @closed="dialogOpen = false">
        <div class="dialog-content wizard-content">
          <p class="eyebrow">STEP {{ wizardStep }} OF 3 · {{ form.mode === 'create' ? 'NEW PEERING' : 'EDIT PEERING' }}</p>
          <h2>{{ form.mode === 'create' ? `Start peering on ${form.node}` : `Edit AS${form.asn} on ${form.node}` }}</h2>
          <div class="wizard-steps" aria-label="Peering wizard steps">
            <span :class="{ active: wizardStep >= 1 }">1. Contact</span>
            <span :class="{ active: wizardStep >= 2 }">2. Interface</span>
            <span :class="{ active: wizardStep >= 3 }">3. Confirm</span>
          </div>

          <template v-if="wizardStep === 1">
            <div class="form-section">
              <h3>Contact information</h3>
              <p class="dialog-note">This information is stored as the peer description so the network operator can contact you about this session.</p>
              <mdui-text-field label="Contact" placeholder="Email, Matrix ID, or other contact" :value="form.contact" @input="form.contact = $event.target.value" required />
            </div>
            <mdui-text-field
              v-if="isAdmin && form.mode === 'create'"
              label="Peer ASN"
              type="number"
              :value="form.asn"
              @input="form.asn = $event.target.value"
            />
          </template>

          <template v-else-if="wizardStep === 2">
            <div class="form-section">
              <h3>WireGuard</h3>
              <mdui-text-field label="Public key" :value="form.publicKey" @input="form.publicKey = $event.target.value" />
              <mdui-text-field label="Endpoint" placeholder="peer.example:22024" :value="form.endpoint" @input="form.endpoint = $event.target.value" />
              <mdui-text-field label="Link MTU" type="number" :value="form.mtu" @input="form.mtu = $event.target.value" />
            </div>
            <div class="form-section">
              <h3>BGP transport</h3>
              <mdui-select label="Transport" :value="form.transportMode" @change="form.transportMode = $event.target.value">
                <mdui-menu-item value="ipv6_link_local">IPv6 link-local</mdui-menu-item>
                <mdui-menu-item value="ipv4">IPv4 transport</mdui-menu-item>
                <mdui-menu-item value="ipv6">IPv6 transport</mdui-menu-item>
              </mdui-select>
              <mdui-text-field label="Remote BGP address" :value="form.remoteAddress" @input="form.remoteAddress = $event.target.value" />
              <label class="switch-row">
                <span>Extended next hop</span>
                <mdui-switch :checked="form.extendedNextHop" @change="form.extendedNextHop = $event.target.checked" />
              </label>
            </div>
          </template>

          <template v-else>
            <div class="confirmation-panel">
              <h3>Review peering request</h3>
              <dl class="review-list">
                <div><dt>Node</dt><dd>{{ form.node }}</dd></div>
                <div><dt>Contact</dt><dd>{{ form.contact }}</dd></div>
              </dl>
            </div>
            <div class="review-columns">
              <section class="review-side review-remote">
                <p class="eyebrow">YOUR DATA · PROVIDE TO US</p>
                <h4>Peer / remote side</h4>
                <dl class="review-list">
                  <div><dt>WireGuard endpoint</dt><dd class="monospace">{{ form.endpoint }}</dd></div>
                  <div><dt>WireGuard public key</dt><dd class="monospace">{{ form.publicKey }}</dd></div>
                  <div><dt>Link MTU</dt><dd>{{ form.mtu }}</dd></div>
                  <div><dt>BGP transport</dt><dd>{{ form.transportMode.replaceAll('_', ' ') }}</dd></div>
                  <div><dt>Remote BGP address</dt><dd class="monospace">{{ form.remoteAddress }}</dd></div>
                  <div><dt>Extended next hop</dt><dd>{{ form.extendedNextHop ? 'Enabled' : 'Disabled' }}</dd></div>
                </dl>
              </section>
              <section class="review-side review-local">
                <p class="eyebrow">OUR DATA · USE TO CONFIGURE YOUR SIDE</p>
                <h4>Node / local side</h4>
                <dl class="review-list">
                  <div><dt>WireGuard endpoint</dt><dd>{{ nodes.find((node) => node.id === form.node)?.peering?.endpoint || 'Not configured' }}</dd></div>
                  <div><dt>WireGuard public key</dt><dd class="monospace">{{ nodes.find((node) => node.id === form.node)?.peering?.publickey || 'Not configured' }}</dd></div>
                  <div><dt>Listen port</dt><dd>Assigned after submission</dd></div>
                  <div><dt>BGP local address</dt><dd>Generated for selected transport</dd></div>
                </dl>
              </section>
            </div>
          </template>
        </div>
        <div slot="action" class="dialog-actions">
          <mdui-button variant="text" @click="wizardStep > 1 ? previousWizardStep() : (dialogOpen = false)">{{ wizardStep > 1 ? 'Back' : 'Cancel' }}</mdui-button>
          <mdui-button v-if="wizardStep < 3" variant="filled" @click="nextWizardStep">Continue</mdui-button>
          <mdui-button v-else variant="filled" :loading="saving" @click="saveSession">Confirm and queue</mdui-button>
        </div>
      </mdui-dialog>

      <mdui-dialog :open="deleteOpen" @closed="deleteOpen = false">
        <div class="dialog-content">
          <p class="eyebrow">REMOVE PEER SESSION</p>
          <h2>Remove AS{{ activeSession?.peer.asn }} on {{ activeSession?.node.id }}?</h2>
          <p>This queues removal of both the WireGuard and BIRD parts of this one peer session.</p>
        </div>
        <div slot="action" class="dialog-actions">
          <mdui-button variant="text" @click="deleteOpen = false">Cancel</mdui-button>
          <mdui-button variant="filled" :loading="saving" @click="deleteSession">Queue removal</mdui-button>
        </div>
      </mdui-dialog>
    </template>
  </main>
</template>
