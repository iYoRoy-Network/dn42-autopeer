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
  description: '',
  publicKey: '',
  endpoint: '',
  transportMode: 'ipv6_link_local',
  remoteAddress: '',
  extendedNextHop: true,
})

setDevAsn(storedDevAsn)

const isAdmin = computed(() => currentUser.value?.role === 'admin')
const statusByNode = computed(() => new Map(statuses.value.map((status) => [status.node, status])))
const sessionCount = computed(() => sessions.value.length)

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

function resetForm(session = null, node = null) {
  const peer = session?.peer
  form.mode = peer ? 'edit' : 'create'
  form.node = session?.node.id ?? node?.id ?? ''
  form.asn = peer ? String(peer.asn) : String(isAdmin.value ? '' : (currentUser.value?.asn ?? ''))
  form.description = peer?.description ?? ''
  form.publicKey = peer?.wireguard_public_key ?? ''
  form.endpoint = peer?.wireguard_endpoint ?? ''
  form.transportMode = peer?.bgp_transport?.mode ?? 'ipv6_link_local'
  form.remoteAddress = peer?.bgp_transport?.remote_address ?? ''
  form.extendedNextHop = peer?.extended_next_hop ?? true
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

function openSession(session) {
  activeSession.value = session
  activePage.value = 'sessions'
  window.setTimeout(() => {
    document.getElementById(`session-${session.node.id}-${session.peer.asn}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  })
}

function asRequestPayload() {
  const wireguard = {
    public_key: form.publicKey,
    endpoint: form.endpoint,
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
      description: form.description || null,
      wireguard,
      bgp: { ...bgp, address_families: ['ipv4', 'ipv6'] },
    }
  }
  return { description: form.description || null, wireguard, bgp }
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
              <p>Choose a node to create a new peer session or manage your existing session there.</p>
            </div>
          </section>

          <section class="node-grid">
            <mdui-card v-for="node in nodes" :key="node.id" class="node-card" variant="outlined">
              <div class="card-heading">
                <div>
                  <p class="eyebrow">{{ node.id }}</p>
                  <h2>{{ node.name }}</h2>
                </div>
                <span class="status-pill" :class="node.peering_enabled ? 'status-online' : 'status-offline'">
                  {{ node.peering_enabled ? 'Open' : 'Closed' }}
                </span>
              </div>
              <dl class="node-details">
                <div><dt>Region</dt><dd>{{ node.region ?? '—' }}</dd></div>
                <div><dt>Country</dt><dd>{{ node.country ?? '—' }}</dd></div>
                <div><dt>BIRD deploy</dt><dd>{{ node.deploy_bird_enabled ? 'Enabled' : 'Disabled' }}</dd></div>
                <div><dt>WireGuard deploy</dt><dd>{{ node.deploy_wireguard_enabled ? 'Enabled' : 'Disabled' }}</dd></div>
              </dl>
              <mdui-divider />
              <div class="node-actions">
                <template v-if="sessions.find((session) => session.node.id === node.id)">
                  <span class="configured-label">Session configured</span>
                  <mdui-button variant="outlined" @click="openSession(sessions.find((session) => session.node.id === node.id))">
                    View session
                  </mdui-button>
                </template>
                <template v-else>
                  <span class="configured-label">No session configured</span>
                  <mdui-button variant="filled" :disabled="!node.peering_enabled" @click="openCreate(node)">
                    Create session
                  </mdui-button>
                </template>
              </div>
            </mdui-card>
          </section>
        </template>

        <template v-else>
          <section class="page-heading sessions-heading">
            <div>
              <p class="eyebrow">YOUR CONFIGURATION</p>
              <h1>My sessions</h1>
              <p>Each session is one peer on one node, containing its WireGuard tunnel and BGP session configuration.</p>
            </div>
            <mdui-button variant="outlined" :loading="loadingStatus" @click="loadStatus">Refresh status</mdui-button>
          </section>

          <section v-if="sessions.length" class="session-list">
            <mdui-card
              v-for="session in sessions"
              :id="`session-${session.node.id}-${session.peer.asn}`"
              :key="`${session.node.id}-${session.peer.asn}`"
              class="session-card"
              :class="{ focused: activeSession?.node.id === session.node.id && activeSession?.peer.asn === session.peer.asn }"
              variant="outlined"
            >
              <div class="session-header">
                <div>
                  <p class="eyebrow">{{ session.node.id }} · PEER SESSION</p>
                  <h2>AS{{ session.peer.asn }} <span>{{ session.peer.description || 'Unnamed session' }}</span></h2>
                </div>
                <div class="session-actions">
                  <mdui-button variant="outlined" @click="openEdit(session)">Edit session</mdui-button>
                  <mdui-button variant="text" @click="activeSession = session; deleteOpen = true">Remove</mdui-button>
                </div>
              </div>

              <div class="session-config">
                <section class="config-block">
                  <p class="eyebrow">WIREGUARD</p>
                  <h3>{{ `dn42_${session.peer.asn}` }}</h3>
                  <dl class="details-grid one-column">
                    <div><dt>Endpoint</dt><dd>{{ session.peer.wireguard_endpoint || 'Not configured' }}</dd></div>
                    <div><dt>Public key</dt><dd class="monospace">{{ session.peer.wireguard_public_key }}</dd></div>
                    <div><dt>Listen port</dt><dd>{{ session.peer.listen_port }}</dd></div>
                  </dl>
                </section>

                <section class="config-block">
                  <p class="eyebrow">BIRD / BGP</p>
                  <h3>{{ `dn42_peer_${session.peer.asn}` }}</h3>
                  <dl class="details-grid one-column">
                    <div><dt>Transport</dt><dd>{{ session.peer.bgp_transport.mode.replaceAll('_', ' ') }}</dd></div>
                    <div><dt>Remote address</dt><dd class="monospace">{{ session.peer.bgp_transport.remote_address }}</dd></div>
                    <div><dt>Address families</dt><dd>{{ session.peer.address_families.join(' + ') }}</dd></div>
                    <div><dt>Extended next hop</dt><dd>{{ session.peer.extended_next_hop ? 'Enabled' : 'Disabled' }}</dd></div>
                  </dl>
                </section>
              </div>

              <section v-if="statusForSession(session)" class="session-status">
                <div class="card-heading">
                  <div>
                    <p class="eyebrow">LIVE STATUS</p>
                    <h3>{{ statusForSession(session).bgp.up ? 'BGP session online' : 'BGP session unavailable' }}</h3>
                  </div>
                  <span class="status-pill" :class="statusForSession(session).bgp.up ? 'status-online' : 'status-offline'">
                    {{ statusForSession(session).bgp.up ? 'Online' : 'Unavailable' }}
                  </span>
                </div>
                <div class="metric-pair">
                  <div><span>WireGuard received</span><strong>{{ formatBytes(statusForSession(session).wireguard.rx_bytes) }}</strong></div>
                  <div><span>WireGuard transmitted</span><strong>{{ formatBytes(statusForSession(session).wireguard.tx_bytes) }}</strong></div>
                  <div><span>BGP imported</span><strong>{{ statusForSession(session).bgp.routes_imported ?? '—' }}</strong></div>
                  <div><span>BGP exported</span><strong>{{ statusForSession(session).bgp.routes_exported ?? '—' }}</strong></div>
                </div>
                <p class="handshake">Last handshake: {{ formatEpoch(statusForSession(session).wireguard.latest_handshake_seconds) }}</p>
              </section>
            </mdui-card>
          </section>

          <section v-else class="empty-state compact-empty">
            <div class="empty-icon" aria-hidden="true">+</div>
            <h2>No peer sessions yet</h2>
            <p>Open the All nodes page and choose a node to create your first WireGuard and BGP session.</p>
            <mdui-button variant="filled" @click="activePage = 'nodes'">Browse nodes</mdui-button>
          </section>
        </template>
      </section>

      <mdui-dialog :open="dialogOpen" @closed="dialogOpen = false">
        <div class="dialog-content">
          <p class="eyebrow">{{ form.mode === 'create' ? 'NEW PEER SESSION' : 'UPDATE PEER SESSION' }}</p>
          <h2>{{ form.mode === 'create' ? `Create session on ${form.node}` : `Edit AS${form.asn} on ${form.node}` }}</h2>
          <p class="dialog-note">A session combines one WireGuard tunnel with its associated BGP configuration.</p>
          <div class="form-section">
            <h3>WireGuard</h3>
            <mdui-text-field label="Public key" :value="form.publicKey" @input="form.publicKey = $event.target.value" />
            <mdui-text-field label="Endpoint" placeholder="peer.example:22024" :value="form.endpoint" @input="form.endpoint = $event.target.value" />
          </div>
          <div class="form-section">
            <h3>BGP</h3>
            <mdui-text-field label="Description" :value="form.description" @input="form.description = $event.target.value" />
            <mdui-select label="Transport" :value="form.transportMode" @change="form.transportMode = $event.target.value">
              <mdui-menu-item value="ipv6_link_local">IPv6 link-local</mdui-menu-item>
              <mdui-menu-item value="ipv4">IPv4 transport</mdui-menu-item>
              <mdui-menu-item value="ipv6">IPv6 transport</mdui-menu-item>
            </mdui-select>
            <mdui-text-field label="Remote address" :value="form.remoteAddress" @input="form.remoteAddress = $event.target.value" />
            <label class="switch-row">
              <span>Extended next hop</span>
              <mdui-switch :checked="form.extendedNextHop" @change="form.extendedNextHop = $event.target.checked" />
            </label>
          </div>
          <mdui-text-field
            v-if="isAdmin && form.mode === 'create'"
            label="Peer ASN"
            type="number"
            :value="form.asn"
            @input="form.asn = $event.target.value"
          />
        </div>
        <div slot="action" class="dialog-actions">
          <mdui-button variant="text" @click="dialogOpen = false">Cancel</mdui-button>
          <mdui-button variant="filled" :loading="saving" @click="saveSession">Queue session change</mdui-button>
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
