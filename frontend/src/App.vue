<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, setDevAsn } from './api'

const storedDevAsn = localStorage.getItem('autopeer-dev-asn') ?? ''
const devAsn = ref(storedDevAsn)
const activePage = ref('peers')
const currentUser = ref(null)
const nodes = ref([])
const peers = ref([])
const statuses = ref([])
const selectedNode = ref('')
const selectedPeerAsn = ref('')
const loading = ref(true)
const loadingStatus = ref(false)
const error = ref('')
const notice = ref('')
const dialogOpen = ref(false)
const deleteOpen = ref(false)
const saving = ref(false)
const pendingJob = ref(null)
const pollTimer = ref(null)

const form = reactive({
  mode: 'create',
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
const selectedNodeInfo = computed(() => nodes.value.find((node) => node.id === selectedNode.value))
const selectedPeer = computed(() =>
  peers.value.find((peer) => String(peer.asn) === String(selectedPeerAsn.value)) ?? null,
)

function statusLabel(value) {
  return value ? 'Online' : 'Unavailable'
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

function resetForm(peer = null) {
  form.mode = peer ? 'edit' : 'create'
  form.asn = peer?.asn ? String(peer.asn) : String(isAdmin.value ? '' : (currentUser.value?.asn ?? ''))
  form.description = peer?.description ?? ''
  form.publicKey = peer?.wireguard_public_key ?? ''
  form.endpoint = peer?.wireguard_endpoint ?? ''
  form.transportMode = peer?.bgp_transport?.mode ?? 'ipv6_link_local'
  form.remoteAddress = peer?.bgp_transport?.remote_address ?? ''
  form.extendedNextHop = peer?.extended_next_hop ?? true
}

async function loadPeers() {
  if (!selectedNode.value || !currentUser.value) {
    peers.value = []
    selectedPeerAsn.value = ''
    return
  }
  peers.value = isAdmin.value
    ? await api.adminPeers(selectedNode.value)
    : await api.peers(selectedNode.value)
  if (!peers.value.some((peer) => String(peer.asn) === String(selectedPeerAsn.value))) {
    selectedPeerAsn.value = peers.value[0] ? String(peers.value[0].asn) : ''
  }
}

async function loadStatus() {
  if (!currentUser.value) return
  loadingStatus.value = true
  try {
    statuses.value = await api.status()
  } catch (requestError) {
    // Metrics are optional in the backend. Show the error without hiding peer configuration.
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
    nodes.value = currentUser.value.role === 'admin' ? await api.adminNodes() : await api.nodes()
    if (!selectedNode.value || !nodes.value.some((node) => node.id === selectedNode.value)) {
      selectedNode.value = nodes.value[0]?.id ?? ''
    }
    await Promise.all([loadPeers(), loadStatus()])
  } catch (requestError) {
    if (requestError.status === 401) {
      currentUser.value = null
      nodes.value = []
      peers.value = []
      statuses.value = []
    } else {
      error.value = requestError.message
    }
  } finally {
    loading.value = false
  }
}

async function chooseNode(event) {
  selectedNode.value = event.target.value
  selectedPeerAsn.value = ''
  await loadPeers()
}

function choosePeer(event) {
  selectedPeerAsn.value = event.target.value
}

function openCreate() {
  resetForm()
  dialogOpen.value = true
}

function openEdit() {
  if (!selectedPeer.value) return
  resetForm(selectedPeer.value)
  dialogOpen.value = true
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
    return { description: form.description || null, wireguard, bgp: { ...bgp, address_families: ['ipv4', 'ipv6'] } }
  }
  return {
    description: form.description || null,
    wireguard,
    bgp,
  }
}

function watchJob(job) {
  pendingJob.value = job
  clearInterval(pollTimer.value)
  pollTimer.value = window.setInterval(async () => {
    try {
      const latest = await api.job(job.id)
      pendingJob.value = latest
      if (['succeeded', 'failed'].includes(latest.status)) {
        clearInterval(pollTimer.value)
        pollTimer.value = null
        if (latest.status === 'succeeded') {
          notice.value = `Job ${latest.id} completed.`
          await Promise.all([loadPeers(), loadStatus()])
        } else {
          error.value = latest.error || `Job ${latest.id} failed.`
        }
      }
    } catch (requestError) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
      error.value = requestError.message
    }
  }, 1500)
}

async function savePeer() {
  if (!selectedNode.value) return
  if (isAdmin.value && form.mode === 'create' && !form.asn.trim()) {
    error.value = 'Peer ASN is required for an administrator-created peer.'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const payload = asRequestPayload()
    const job = form.mode === 'create'
      ? (isAdmin.value
        ? await api.createAdminPeer(selectedNode.value, Number(form.asn), payload)
        : await api.createPeer(selectedNode.value, payload))
      : (isAdmin.value
        ? await api.patchAdminPeer(selectedNode.value, Number(form.asn), payload)
        : await api.patchPeer(selectedNode.value, Number(form.asn), payload))
    dialogOpen.value = false
    notice.value = `Queued ${job.kind} for AS${form.asn}.`
    watchJob(job)
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    saving.value = false
  }
}

async function deletePeer() {
  if (!selectedPeer.value || !selectedNode.value) return
  saving.value = true
  error.value = ''
  try {
    const job = isAdmin.value
      ? await api.deleteAdminPeer(selectedNode.value, selectedPeer.value.asn)
      : await api.deletePeer(selectedNode.value, selectedPeer.value.asn)
    deleteOpen.value = false
    notice.value = `Queued removal for AS${selectedPeer.value.asn}.`
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
    peers.value = []
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
          <div class="brand-mark" aria-hidden="true">⟷</div>
          <div>
            <p class="eyebrow">DN42 CONTROL PLANE</p>
            <h1 id="login-title">iyoroynet autopeer</h1>
            <p>Manage the peer that belongs to your ASN, with configuration changes queued and applied serially.</p>
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
      <aside class="navigation" aria-label="Primary navigation">
        <div class="rail-brand" aria-label="iyoroynet autopeer">⟷</div>
        <mdui-navigation-rail :value="activePage" @change="activePage = $event.target.value">
          <mdui-navigation-rail-item value="peers" icon="hub" active-icon="hub">Peers</mdui-navigation-rail-item>
          <mdui-navigation-rail-item value="status" icon="monitoring" active-icon="monitoring">Status</mdui-navigation-rail-item>
        </mdui-navigation-rail>
        <mdui-button-icon class="logout-button" icon="logout" aria-label="Sign out" @click="logout" />
      </aside>

      <section class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">{{ activePage === 'peers' ? 'PEER CONFIGURATION' : 'SESSION TELEMETRY' }}</p>
            <h1>{{ activePage === 'peers' ? 'Your DN42 peer' : 'Peer status' }}</h1>
          </div>
          <div class="identity" aria-label="Current identity">
            <div class="identity-avatar">{{ currentUser.display_name?.slice(0, 1) ?? 'A' }}</div>
            <div>
              <strong>{{ currentUser.display_name || `AS${currentUser.asn}` }}</strong>
              <span>AS{{ currentUser.asn }} · {{ currentUser.role }}</span>
            </div>
          </div>
        </header>

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

        <template v-if="activePage === 'peers'">
          <section class="toolbar" aria-label="Peer controls">
            <mdui-select label="Node" :value="selectedNode" @change="chooseNode">
              <mdui-menu-item v-for="node in nodes" :key="node.id" :value="node.id">
                {{ node.name }} · {{ node.id }}
              </mdui-menu-item>
            </mdui-select>
            <mdui-select
              v-if="peers.length"
              label="Peer"
              :value="selectedPeerAsn"
              @change="choosePeer"
            >
              <mdui-menu-item v-for="peer in peers" :key="peer.asn" :value="String(peer.asn)">
                AS{{ peer.asn }}{{ peer.description ? ` · ${peer.description}` : '' }}
              </mdui-menu-item>
            </mdui-select>
            <div class="toolbar-spacer" />
            <mdui-button v-if="!selectedPeer" variant="filled" icon="add" @click="openCreate">Add peer</mdui-button>
            <template v-else>
              <mdui-button variant="outlined" icon="edit" @click="openEdit">Edit peer</mdui-button>
              <mdui-button variant="text" icon="delete" @click="deleteOpen = true">Delete</mdui-button>
            </template>
          </section>

          <section v-if="selectedNodeInfo" class="node-summary">
            <span class="status-dot" :class="selectedNodeInfo.peering_enabled ? 'status-good' : 'status-muted'" aria-hidden="true" />
            <span>{{ selectedNodeInfo.name }} · region {{ selectedNodeInfo.region ?? '—' }}</span>
            <span class="node-id">{{ selectedNodeInfo.id }}</span>
          </section>

          <section v-if="selectedPeer" class="peer-layout">
            <mdui-card class="peer-overview" variant="outlined">
              <div class="card-heading">
                <div>
                  <p class="eyebrow">BGP SESSION</p>
                  <h2>AS{{ selectedPeer.asn }}</h2>
                </div>
                <mdui-chip variant="assist">{{ selectedPeer.bgp_transport.mode.replaceAll('_', ' ') }}</mdui-chip>
              </div>
              <p class="peer-description">{{ selectedPeer.description || 'No description' }}</p>
              <mdui-divider />
              <dl class="details-grid">
                <div><dt>Remote address</dt><dd>{{ selectedPeer.bgp_transport.remote_address }}</dd></div>
                <div><dt>Extended next hop</dt><dd>{{ selectedPeer.extended_next_hop ? 'Enabled' : 'Disabled' }}</dd></div>
                <div><dt>Address families</dt><dd>{{ selectedPeer.address_families.join(' + ') }}</dd></div>
                <div><dt>Listen port</dt><dd>{{ selectedPeer.listen_port }}</dd></div>
              </dl>
            </mdui-card>

            <mdui-card class="peer-overview" variant="outlined">
              <div class="card-heading">
                <div>
                  <p class="eyebrow">WIREGUARD TUNNEL</p>
                  <h2>{{ `dn42_${selectedPeer.asn}` }}</h2>
                </div>
                <mdui-chip variant="assist">one endpoint</mdui-chip>
              </div>
              <p class="endpoint">{{ selectedPeer.wireguard_endpoint || 'Endpoint not set' }}</p>
              <mdui-divider />
              <dl class="details-grid one-column">
                <div><dt>Public key</dt><dd class="monospace">{{ selectedPeer.wireguard_public_key }}</dd></div>
              </dl>
            </mdui-card>
          </section>

          <section v-else class="empty-state">
            <div class="empty-icon" aria-hidden="true">⊹</div>
            <h2>No peer on this node</h2>
            <p>Create the WireGuard and BGP session for AS{{ currentUser.asn }} on {{ selectedNode || 'a node' }}.</p>
            <mdui-button variant="filled" icon="add" @click="openCreate">Add peer</mdui-button>
          </section>
        </template>

        <template v-else>
          <section class="status-toolbar">
            <div>
              <h2>AS{{ currentUser.asn }} across monitored nodes</h2>
              <p>Exporter-derived values. A missing value means the exporter has not provided that metric.</p>
            </div>
            <mdui-button variant="outlined" icon="refresh" :loading="loadingStatus" @click="loadStatus">Refresh</mdui-button>
          </section>

          <section v-if="statuses.length" class="status-grid">
            <mdui-card v-for="status in statuses" :key="status.node" class="status-card" variant="outlined">
              <div class="card-heading">
                <div>
                  <p class="eyebrow">{{ status.node }}</p>
                  <h2>{{ status.interface }}</h2>
                </div>
                <mdui-chip :variant="status.bgp.up ? 'assist' : 'filter'">
                  {{ statusLabel(status.bgp.up) }}
                </mdui-chip>
              </div>
              <div class="metric-pair">
                <div><span>WireGuard received</span><strong>{{ formatBytes(status.wireguard.rx_bytes) }}</strong></div>
                <div><span>WireGuard transmitted</span><strong>{{ formatBytes(status.wireguard.tx_bytes) }}</strong></div>
              </div>
              <mdui-divider />
              <dl class="details-grid">
                <div><dt>BGP imported</dt><dd>{{ status.bgp.routes_imported ?? '—' }}</dd></div>
                <div><dt>BGP exported</dt><dd>{{ status.bgp.routes_exported ?? '—' }}</dd></div>
                <div><dt>Last handshake</dt><dd>{{ formatEpoch(status.wireguard.latest_handshake_seconds) }}</dd></div>
                <div><dt>Protocol</dt><dd class="monospace">{{ status.protocol }}</dd></div>
              </dl>
            </mdui-card>
          </section>
          <section v-else class="empty-state">
            <div class="empty-icon" aria-hidden="true">⌁</div>
            <h2>No monitored session data</h2>
            <p>Configure metrics targets for the WireGuard, BIRD, and node exporters to populate this view.</p>
          </section>
        </template>
      </section>

      <mdui-dialog :open="dialogOpen" @closed="dialogOpen = false">
        <div class="dialog-content">
          <p class="eyebrow">{{ form.mode === 'create' ? 'NEW PEER' : 'UPDATE PEER' }}</p>
          <h2>{{ form.mode === 'create' ? `Add AS${currentUser.asn}` : `Edit AS${form.asn}` }}</h2>
          <p class="dialog-note">
            {{ isAdmin ? 'Administrator actions are still limited to one node and one peer file.' : 'Only the fixed peer file for your ASN can be changed.' }}
          </p>
          <div class="form-grid">
            <mdui-text-field
              v-if="isAdmin && form.mode === 'create'"
              label="Peer ASN"
              type="number"
              :value="form.asn"
              @input="form.asn = $event.target.value"
            />
            <mdui-text-field label="Description" :value="form.description" @input="form.description = $event.target.value" />
            <mdui-text-field label="WireGuard public key" :value="form.publicKey" @input="form.publicKey = $event.target.value" />
            <mdui-text-field label="WireGuard endpoint" placeholder="peer.example:22024" :value="form.endpoint" @input="form.endpoint = $event.target.value" />
            <mdui-select label="BGP transport" :value="form.transportMode" @change="form.transportMode = $event.target.value">
              <mdui-menu-item value="ipv6_link_local">IPv6 link-local</mdui-menu-item>
              <mdui-menu-item value="ipv4">IPv4 transport</mdui-menu-item>
              <mdui-menu-item value="ipv6">IPv6 transport</mdui-menu-item>
            </mdui-select>
            <mdui-text-field label="BGP remote address" :value="form.remoteAddress" @input="form.remoteAddress = $event.target.value" />
            <label class="switch-row">
              <span>Extended next hop</span>
              <mdui-switch :checked="form.extendedNextHop" @change="form.extendedNextHop = $event.target.checked" />
            </label>
          </div>
        </div>
        <div slot="action" class="dialog-actions">
          <mdui-button variant="text" @click="dialogOpen = false">Cancel</mdui-button>
          <mdui-button variant="filled" :loading="saving" @click="savePeer">Queue change</mdui-button>
        </div>
      </mdui-dialog>

      <mdui-dialog :open="deleteOpen" @closed="deleteOpen = false">
        <div class="dialog-content">
          <p class="eyebrow">REMOVE PEER</p>
          <h2>Remove AS{{ selectedPeer?.asn }}?</h2>
          <p>This queues the removal of only this peer's BIRD and WireGuard configuration on {{ selectedNode }}.</p>
        </div>
        <div slot="action" class="dialog-actions">
          <mdui-button variant="text" @click="deleteOpen = false">Cancel</mdui-button>
          <mdui-button variant="filled" :loading="saving" @click="deletePeer">Queue removal</mdui-button>
        </div>
      </mdui-dialog>
    </template>
  </main>
</template>
