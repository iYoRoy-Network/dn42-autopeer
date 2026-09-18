<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ThunderboltOutlined, EyeOutlined, GlobalOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '@/store'
import { formatBytes, formatRate, nodeTitle } from '@/common/helper'
import type { NodeSummary } from '@/common/packetHandler'

const { t } = useI18n()
const router = useRouter()
const store = useAutopeer()

onMounted(() => {
  if (!store.currentUser.value) store.bootstrap()
})

const stackLabel = (node: NodeSummary): string => {
  const stack = node.peering?.protocol_stack ?? 'dual_stack'
  if (stack === 'ipv4') return t('nodes.ipv4Only')
  if (stack === 'ipv6') return t('nodes.ipv6Only')
  return t('nodes.dualStack')
}

const startPeering = (node: NodeSummary) => {
  store.openCreate(node)
  router.push({ name: 'peer-create', params: { node: node.id } })
}

const openNode = (node: NodeSummary) => {
  router.push({ name: 'node', params: { node: node.id } })
}
</script>

<template>
  <div class="nodes-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">{{ t('nodes.eyebrow') }}</p>
        <h1>{{ t('nodes.title') }}</h1>
        <p class="subtitle">{{ t('nodes.subtitle') }}</p>
      </div>
    </section>

    <a-spin :spinning="store.loading.value">
      <a-empty v-if="!store.loading.value && !store.nodes.value.length" :description="t('common.notFound')" />
      <a-row v-else :gutter="[16, 16]">
        <a-col v-for="node in store.nodes.value" :key="node.id" :xs="24" :sm="12" :lg="8">
          <a-card class="node-card" hoverable>
            <div class="node-head">
              <div class="node-title">
                <span class="node-icon"><global-outlined /></span>
                <div>
                  <div class="node-name">{{ nodeTitle(node) }}</div>
                  <div class="node-sub">{{ node.peering?.subtitle || node.id }}</div>
                </div>
              </div>
              <a-tag color="blue">{{ stackLabel(node) }}</a-tag>
            </div>

            <a-row :gutter="8" class="node-stats">
              <a-col :span="8">
                <a-statistic :title="t('nodes.peers')" :value="node.peer_count" />
                <span class="stat-note">{{ (node.online_peer_count ?? 0) }} {{ t('nodes.online') }}</span>
              </a-col>
              <a-col :span="16">
                <a-statistic
                  :title="t('nodes.traffic')"
                  :value="formatBytes(node.runtime_metrics?.rx_bytes)"
                  :suffix="''"
                />
                <span class="stat-note">
                  ↓ {{ formatRate(node.runtime_metrics?.rx_bytes_per_second) }}
                  · ↑ {{ formatRate(node.runtime_metrics?.tx_bytes_per_second) }}
                </span>
              </a-col>
            </a-row>

            <div class="node-actions">
              <a-button type="primary" :disabled="!node.peering_enabled" @click="startPeering(node)">
                <thunderbolt-outlined />
                {{ t('nodes.startPeering') }}
              </a-button>
              <a-button @click="openNode(node)">
                <eye-outlined />
                {{ t('common.details') }}
              </a-button>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<style scoped>
.nodes-page {
  padding: 32px 24px 64px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-heading {
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

.node-card {
  border-radius: 10px;
}

.node-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.node-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.node-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 8px;
  background: #e6f4ff;
  color: #1890ff;
  font-size: 18px;
}

.node-name {
  font-weight: 600;
  font-size: 16px;
}

.node-sub {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.node-stats {
  margin-bottom: 16px;
}

.stat-note {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.node-actions {
  display: flex;
  gap: 8px;
}

.dark .subtitle,
.dark .node-sub,
.dark .stat-note {
  color: rgba(255, 255, 255, 0.55);
}
</style>
