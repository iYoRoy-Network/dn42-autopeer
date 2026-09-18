<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '../store'
import { formatBytes, formatHandshake, nodeTitle } from '../common/helper'

const { t } = useI18n()
const store = useAutopeer()

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  edit: []
  remove: []
}>()

const session = computed(() => store.activeSession.value)
const status = computed(() => (session.value ? store.statusForSession(session.value) : undefined))

const transportLabel = (mode?: string): string => (mode ? mode.replaceAll('_', ' ') : '—')
</script>

<template>
  <a-drawer
    :open="props.open"
    :title="session ? `AS${session.peer.asn} · ${nodeTitle(session.node)}` : ''"
    width="560"
    @close="emit('update:open', false)"
  >
    <template v-if="session">
      <a-descriptions :column="1" bordered size="small" :title="t('peer.title')">
        <a-descriptions-item :label="t('peer.contact')">
          {{ session.peer.description || '—' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.endpoint')">
          <span class="mono">{{ session.peer.wireguard_endpoint || '—' }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.publicKey')">
          <span class="mono">{{ session.peer.wireguard_public_key }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.mtu')">{{ session.peer.mtu }}</a-descriptions-item>
        <a-descriptions-item :label="t('peer.transport')">
          {{ transportLabel(session.peer.bgp_transport?.mode) }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.remoteAddress')">
          <span class="mono">{{ session.peer.bgp_transport?.remote_address }}</span>
        </a-descriptions-item>
      </a-descriptions>

      <a-descriptions
        v-if="session.peer.connection_info"
        :column="1"
        bordered
        size="small"
        :title="t('peer.ourInfo')"
        style="margin-top: 16px"
      >
        <a-descriptions-item :label="t('peer.endpoint')">
          <span class="mono">{{
            session.peer.connection_info.wireguard_endpoint || t('peer.notConfigured')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.publicKey')">
          <span class="mono">{{
            session.peer.connection_info.public_key || t('peer.notConfigured')
          }}</span>
        </a-descriptions-item>
        <a-descriptions-item :label="t('peer.localAddress')">
          <span class="mono">{{ session.peer.connection_info.bgp_local_address }}</span>
        </a-descriptions-item>
      </a-descriptions>

      <a-row v-if="status" :gutter="[12, 12]" class="metrics">
        <a-col :span="8">
          <a-statistic
            :title="t('peer.bgpStatus')"
            :value="status.bgp?.up ? t('session.established') : t('session.unavailable')"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic :title="t('peer.imported')" :value="status.bgp?.routes_imported ?? '—'" />
        </a-col>
        <a-col :span="8">
          <a-statistic :title="t('peer.exported')" :value="status.bgp?.routes_exported ?? '—'" />
        </a-col>
        <a-col :span="8">
          <a-statistic :title="t('peer.received')" :value="formatBytes(status.wireguard?.rx_bytes)" />
        </a-col>
        <a-col :span="8">
          <a-statistic :title="t('peer.transmitted')" :value="formatBytes(status.wireguard?.tx_bytes)" />
        </a-col>
        <a-col :span="8">
          <a-statistic :title="t('peer.lastHandshake')" :value="formatHandshake(status, t)" />
        </a-col>
      </a-row>

      <div class="actions">
        <a-button @click="emit('edit')">
          <edit-outlined />
          {{ t('session.edit') }}
        </a-button>
        <a-popconfirm
          :title="t('session.deleteConfirm')"
          :description="t('session.deleteHint')"
          @confirm="emit('remove')"
        >
          <a-button danger>
            <delete-outlined />
            {{ t('session.delete') }}
          </a-button>
        </a-popconfirm>
      </div>
    </template>
  </a-drawer>
</template>

<style scoped>
.mono {
  font-family: 'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace;
  font-size: 0.9em;
  word-break: break-all;
}

.metrics {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.02);
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 24px;
}
</style>
