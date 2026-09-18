<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeftOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '@/store'
import { formatBytes, formatRate, nodeTitle } from '@/common/helper'
import type { Session } from '@/common/packetHandler'
import SessionTable from '@/components/SessionTable.vue'
import SessionDrawer from '@/components/SessionDrawer.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAutopeer()

const drawerOpen = ref(false)

onMounted(async () => {
  if (!store.currentUser.value) await store.bootstrap()
})

const node = computed(() => store.nodes.value.find((n) => n.id === route.params.node))
const nodeSessions = computed(() =>
  store.sessions.value.filter((s) => s.node.id === route.params.node),
)

const startPeering = () => {
  if (!node.value) return
  store.openCreate(node.value)
  router.push({ name: 'peer-create', params: { node: node.value.id } })
}

const openView = (session: Session) => {
  store.activeSession.value = session
  drawerOpen.value = true
}

const openEdit = (session: Session) => {
  store.openEdit(session)
  router.push({
    name: 'peer-edit',
    params: { node: session.node.id, asn: String(session.peer.asn) },
  })
}

const remove = (session: Session) => {
  store.deleteSession(session)
}
</script>

<template>
  <div class="node-page">
    <a-button type="text" class="back" @click="router.push({ name: 'landing' })">
      <arrow-left-outlined />
      {{ t('nodes.back') }}
    </a-button>

    <template v-if="node">
      <section class="node-heading">
        <div>
          <p class="eyebrow">{{ node.id }}</p>
          <h1>{{ nodeTitle(node) }}</h1>
          <p class="subtitle">{{ node.peering?.subtitle || 'DN42 WireGuard peering node' }}</p>
        </div>
        <a-button type="primary" :disabled="!node.peering_enabled" @click="startPeering">
          <thunderbolt-outlined />
          {{ t('nodes.startPeering') }}
        </a-button>
      </section>

      <a-row :gutter="16" class="stats">
        <a-col :xs="12" :sm="6">
          <a-statistic :title="t('nodes.peers')" :value="node.peer_count" />
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-statistic :title="t('nodes.online')" :value="node.online_peer_count ?? 0" />
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-statistic
            :title="t('peer.received')"
            :value="formatBytes(node.runtime_metrics?.rx_bytes)"
          />
        </a-col>
        <a-col :xs="12" :sm="6">
          <a-statistic
            :title="t('peer.transmitted')"
            :value="formatBytes(node.runtime_metrics?.tx_bytes)"
          />
        </a-col>
      </a-row>

      <a-card class="sessions-card" :title="t('nodes.peerSessions')">
        <template #extra>
          <span class="card-extra">
            ↓ {{ formatRate(node.runtime_metrics?.rx_bytes_per_second) }}
            · ↑ {{ formatRate(node.runtime_metrics?.tx_bytes_per_second) }}
          </span>
        </template>

        <SessionTable
          v-if="nodeSessions.length"
          :sessions="nodeSessions"
          @view="openView"
          @edit="openEdit"
          @remove="remove"
        />
        <div v-else class="empty-wrap">
          <a-empty :description="t('nodes.noSessions')" />
          <p class="empty-hint">{{ t('nodes.noSessionsHint') }}</p>
        </div>
      </a-card>
    </template>

    <a-result v-else status="404" :title="t('common.notFound')" />

    <SessionDrawer
      v-model:open="drawerOpen"
      @edit="store.activeSession.value && openEdit(store.activeSession.value)"
      @remove="store.activeSession.value && remove(store.activeSession.value)"
    />
  </div>
</template>

<style scoped>
.node-page {
  padding: 32px 24px 64px;
  max-width: 1200px;
  margin: 0 auto;
}

.back {
  margin-bottom: 16px;
  padding-left: 0;
}

.node-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 4px;
  color: #1890ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.node-heading h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
}

.subtitle {
  color: rgba(0, 0, 0, 0.45);
  margin: 8px 0 0;
}

.stats {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.02);
}

.card-extra {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.empty-hint {
  color: rgba(0, 0, 0, 0.45);
}

.empty-wrap {
  text-align: center;
  padding: 24px 0;
}

.dark .subtitle,
.dark .card-extra,
.dark .empty-hint {
  color: rgba(255, 255, 255, 0.55);
}
</style>
