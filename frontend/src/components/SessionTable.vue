<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { EyeOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import type { Session } from '../common/packetHandler'
import { formatBytes, nodeTitle } from '../common/helper'
import { useAutopeer } from '../store'

const { t } = useI18n()
const store = useAutopeer()

const props = defineProps<{
  sessions: Session[]
  loading?: boolean
}>()

const emit = defineEmits<{
  view: [session: Session]
  edit: [session: Session]
  remove: [session: Session]
}>()

const transportLabel = (mode?: string): string => (mode ? mode.replaceAll('_', ' ') : '—')

const bgpState = (session: Session): 'established' | 'down' | 'unavailable' => {
  const bgp = store.statusForSession(session)?.bgp
  if (bgp?.up === true) return 'established'
  if (bgp?.up === false) return 'down'
  return 'unavailable'
}

const columns = computed<any[]>(() => [
  { title: t('session.node'), key: 'node', dataIndex: 'node' },
  { title: t('session.asn'), key: 'asn', dataIndex: 'asn' },
  { title: t('session.type'), key: 'type', dataIndex: 'type' },
  { title: t('session.status'), key: 'status', dataIndex: 'status', align: 'center' },
  { title: '↓ / ↑', key: 'traffic', dataIndex: 'traffic' },
  { title: t('session.actions'), key: 'actions', dataIndex: 'actions', align: 'right' },
])
</script>

<template>
  <a-table
    :columns="columns"
    :data-source="sessions"
    :loading="loading"
    :row-key="(r: Session) => `${r.node.id}-${r.peer.asn}`"
    size="middle"
    :pagination="false"
    :scroll="{ x: 'max-content' }"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'node'">
        <div class="cell-node">
          <span class="cell-avatar">{{ nodeTitle(record.node).slice(0, 2).toUpperCase() }}</span>
          <div class="cell-node-text">
            <span class="cell-title">{{ nodeTitle(record.node) }}</span>
            <span class="cell-sub">{{ record.node.peering?.subtitle || record.node.id }}</span>
          </div>
        </div>
      </template>

      <template v-else-if="column.key === 'asn'">
        <div class="cell-asn">
          <span class="cell-title mono">AS{{ record.peer.asn }}</span>
          <span class="cell-sub">{{ record.peer.description || '—' }}</span>
        </div>
      </template>

      <template v-else-if="column.key === 'type'">
        <div class="cell-type">
          <a-tag>{{ transportLabel(record.peer.bgp_transport?.mode) }}</a-tag>
          <a-tag v-for="af in record.peer.address_families" :key="af" color="blue">{{ af }}</a-tag>
        </div>
      </template>

      <template v-else-if="column.key === 'status'">
        <a-tag v-if="bgpState(record) === 'established'" color="green">
          {{ t('session.established') }}
        </a-tag>
        <a-tag v-else-if="bgpState(record) === 'down'" color="red">{{ t('session.down') }}</a-tag>
        <a-tag v-else color="orange">{{ t('session.unavailable') }}</a-tag>
      </template>

      <template v-else-if="column.key === 'traffic'">
        <span class="cell-sub">
          ↓ {{ formatBytes(store.statusForSession(record)?.wireguard?.rx_bytes) }}
          · ↑ {{ formatBytes(store.statusForSession(record)?.wireguard?.tx_bytes) }}
        </span>
      </template>

      <template v-else-if="column.key === 'actions'">
        <a-button-group size="small">
          <a-tooltip :title="t('session.view')">
            <a-button type="primary" size="small" @click="emit('view', record)">
              <eye-outlined />
            </a-button>
          </a-tooltip>
          <a-tooltip :title="t('session.edit')">
            <a-button size="small" @click="emit('edit', record)">
              <edit-outlined />
            </a-button>
          </a-tooltip>
          <a-popconfirm
            placement="bottomRight"
            :title="t('session.deleteConfirm')"
            :description="t('session.deleteHint')"
            @confirm="emit('remove', record)"
          >
            <a-tooltip :title="t('session.delete')">
              <a-button danger size="small">
                <delete-outlined />
              </a-button>
            </a-tooltip>
          </a-popconfirm>
        </a-button-group>
      </template>
    </template>
  </a-table>
</template>

<style scoped>
.cell-node {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cell-avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 8px;
  background: #e6f4ff;
  color: #1890ff;
  font-weight: 700;
  font-size: 13px;
}

.cell-node-text,
.cell-asn {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cell-title {
  font-weight: 600;
}

.cell-sub {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}

.dark .cell-sub {
  color: rgba(255, 255, 255, 0.55);
}

.cell-type {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.mono {
  font-family: 'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace;
}
</style>
