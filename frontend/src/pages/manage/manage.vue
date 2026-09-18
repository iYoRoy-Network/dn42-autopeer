<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '@/store'
import { formatBytes, nodeTitle } from '@/common/helper'
import type { Session } from '@/common/packetHandler'
import SessionTable from '@/components/SessionTable.vue'
import SessionDrawer from '@/components/SessionDrawer.vue'

const { t } = useI18n()
const router = useRouter()
const store = useAutopeer()

const drawerOpen = ref(false)
const activeTab = ref('all')

onMounted(() => {
  if (!store.currentUser.value) store.bootstrap()
})

const nodeTabs = computed(() => {
  const ids = new Set(store.sessions.value.map((s) => s.node.id))
  return [...ids].map((id) => {
    const first = store.sessions.value.find((s) => s.node.id === id)
    return { key: id, label: first ? nodeTitle(first.node) : id }
  })
})

const tabSessions = computed<Session[]>(() => {
  if (activeTab.value === 'all') return store.sessions.value
  return store.sessions.value.filter((s) => s.node.id === activeTab.value)
})

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
  <div class="sessions-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">{{ t('sessions.eyebrow') }}</p>
        <h1>{{ t('sessions.title') }}</h1>
        <p class="subtitle">{{ t('sessions.subtitle') }}</p>
      </div>
      <div class="heading-actions">
        <a-button :loading="store.loadingStatus.value" @click="store.loadStatus()">
          <reload-outlined />
          {{ t('common.refresh') }}
        </a-button>
        <a-button type="primary" @click="router.push({ name: 'landing' })">
          <plus-outlined />
          {{ t('nodes.startPeering') }}
        </a-button>
      </div>
    </section>

    <a-row :gutter="[12, 12]" class="summary">
      <a-col :xs="12" :sm="8" :lg="4">
        <a-card size="small">
          <a-statistic :title="t('sessions.summary.health')" :value="store.onlineSessionCount.value" :suffix="`/ ${store.sessionCount.value}`" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="8" :lg="4">
        <a-card size="small">
          <a-statistic :title="t('sessions.summary.issues')" :value="store.sessionCount.value - store.onlineSessionCount.value" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="8" :lg="4">
        <a-card size="small">
          <a-statistic :title="t('sessions.summary.routes')" :value="store.totalImportedRoutes.value + store.totalExportedRoutes.value" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="12" :lg="6">
        <a-card size="small">
          <a-statistic :title="t('sessions.summary.received')" :value="formatBytes(store.totalReceived.value)" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="12" :lg="6">
        <a-card size="small">
          <a-statistic :title="t('sessions.summary.transmitted')" :value="formatBytes(store.totalTransmitted.value)" />
        </a-card>
      </a-col>
    </a-row>

    <div
      v-if="!store.sessions.value.length && !store.loading.value"
      class="empty-wrap"
    >
      <a-empty :description="t('sessions.empty')" />
      <a-button type="primary" @click="router.push({ name: 'landing' })">
        {{ t('sessions.browse') }}
      </a-button>
    </div>

    <a-card v-else>
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="all" :tab="t('sessions.allNodes')">
          <SessionTable :sessions="tabSessions" @view="openView" @edit="openEdit" @remove="remove" />
        </a-tab-pane>
        <a-tab-pane v-for="tab in nodeTabs" :key="tab.key" :tab="tab.label">
          <SessionTable :sessions="tabSessions" @view="openView" @edit="openEdit" @remove="remove" />
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <SessionDrawer
      v-model:open="drawerOpen"
      @edit="store.activeSession.value && openEdit(store.activeSession.value)"
      @remove="store.activeSession.value && remove(store.activeSession.value)"
    />
  </div>
</template>

<style scoped>
.sessions-page {
  padding: 32px 24px 64px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-heading {
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

.page-heading h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
}

.subtitle {
  color: rgba(0, 0, 0, 0.45);
  margin: 8px 0 0;
}

.heading-actions {
  display: flex;
  gap: 8px;
}

.summary {
  margin-bottom: 24px;
}

.empty-wrap {
  text-align: center;
  padding: 24px 0;
}

.dark .subtitle {
  color: rgba(255, 255, 255, 0.55);
}
</style>
