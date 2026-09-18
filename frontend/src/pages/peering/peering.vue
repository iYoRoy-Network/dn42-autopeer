<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeftOutlined, CheckOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '@/store'
import { nodeTitle } from '@/common/helper'
import type { NodeSummary } from '@/common/packetHandler'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAutopeer()

onMounted(async () => {
  if (!store.currentUser.value) await store.bootstrap()
  const node = store.nodes.value.find((n) => n.id === route.params.node)
  if (route.params.asn) {
    const existing = store.sessions.value.find(
      (s) => s.node.id === route.params.node && String(s.peer.asn) === String(route.params.asn),
    )
    store.resetForm(existing || null, node || null)
  } else {
    store.resetForm(null, node || null)
  }
})

const step = computed(() => store.wizardStep.value)
const isEdit = computed(() => store.form.mode === 'edit')
const isAdmin = computed(() => store.isAdmin.value)

const node = computed<NodeSummary | undefined>(() =>
  store.nodes.value.find((n) => n.id === route.params.node),
)

const title = computed(() => {
  if (isEdit.value) return t('wizard.editTitle', { asn: store.form.asn, node: store.form.node })
  return t('wizard.createTitle', { node: store.form.node })
})

const cancel = () => router.push({ name: 'node', params: { node: route.params.node } })

const next = () => store.nextWizardStep()

const back = () => {
  if (step.value > 1) store.previousWizardStep()
  else cancel()
}

const submit = async () => {
  const ok = await store.saveSession()
  if (ok) router.push({ name: 'node', params: { node: route.params.node } })
}

const peerAddress = computed(() => {
  if (!store.form.ipv6Enabled) return t('wizard.review.notUsed')
  return store.form.ipv6Mode === 'global' ? store.form.ipv6Address : store.form.ipv6LinkLocalAddress
})
</script>

<template>
  <div class="peering-page">
    <a-button type="text" class="back" @click="back">
      <arrow-left-outlined />
      {{ t('wizard.back') }}
    </a-button>

    <section class="heading">
      <p class="eyebrow">{{ isEdit ? t('wizard.edit') : t('wizard.new') }}</p>
      <h1>{{ title }}</h1>
      <p class="subtitle">{{ t('wizard.subtitle') }}</p>
    </section>

    <a-steps :current="step - 1" class="steps">
      <a-step :title="t('wizard.step1')" />
      <a-step :title="t('wizard.step2')" />
      <a-step :title="t('wizard.step3')" />
    </a-steps>

    <a-card class="panel" v-if="step === 1" :title="t('wizard.step1Title')">
      <p class="hint">{{ t('wizard.step1Hint') }}</p>
      <a-form layout="vertical">
        <a-form-item :label="t('wizard.contact')" required>
          <a-input
            v-model:value="store.form.contact"
            :placeholder="t('wizard.contactPlaceholder')"
            size="large"
          />
        </a-form-item>

        <a-form-item :label="t('wizard.capabilities')">
          <div class="capability">
            <div class="cap-text">
              <b>{{ t('wizard.wireguard') }}</b>
              <span class="hint">{{ t('wizard.wireguardHint') }}</span>
            </div>
            <check-outlined class="cap-check" />
          </div>
        </a-form-item>

        <a-form-item v-if="isAdmin && !isEdit" :label="t('wizard.peerAsn')" required>
          <a-input-number
            v-model:value="store.form.asn"
            :min="1"
            :max="4294967295"
            style="width: 100%"
            size="large"
          />
        </a-form-item>
      </a-form>
      <p class="hint">{{ t('wizard.bgpNote') }}</p>
    </a-card>

    <a-card class="panel" v-else-if="step === 2" :title="t('wizard.step2Title')">
      <p class="hint">{{ t('wizard.step2Hint') }}</p>
      <a-form layout="vertical">
        <a-divider orientation="left">{{ t('wizard.wireguard') }}</a-divider>
        <a-form-item :label="t('wizard.publicKey')" required>
          <a-input v-model:value="store.form.publicKey" size="large" />
        </a-form-item>
        <a-form-item :label="t('wizard.endpoint')" required>
          <a-input
            v-model:value="store.form.endpoint"
            :placeholder="t('wizard.endpointPlaceholder')"
            size="large"
          />
        </a-form-item>
        <a-form-item :label="t('wizard.mtu')">
          <a-input-number v-model:value="store.form.mtu" :min="576" :max="9000" style="width: 100%" size="large" />
        </a-form-item>

        <a-divider orientation="left">{{ t('wizard.routeExchange') }}</a-divider>

        <div class="option-row">
          <div>
            <b>{{ t('wizard.mpBgp') }}</b>
            <span class="hint">{{ t('wizard.mpBgpHint') }}</span>
          </div>
          <a-switch :checked="store.form.mpBgp" @change="store.setMpBgp($event)" />
        </div>

        <div class="option-row">
          <div>
            <b>{{ t('wizard.ipv4') }}</b>
            <span class="hint">{{ store.form.mpBgp ? t('wizard.ipv4Carried') : t('wizard.ipv4Independent') }}</span>
          </div>
          <a-switch v-model:checked="store.form.ipv4Enabled" :disabled="store.form.mpBgp" />
        </div>
        <a-form-item v-if="store.form.ipv4Enabled && !store.form.mpBgp" :label="t('wizard.ipv4Address')" required>
          <a-input v-model:value="store.form.ipv4Address" size="large" />
        </a-form-item>

        <div class="option-row">
          <div>
            <b>{{ t('wizard.ipv6') }}</b>
            <span class="hint">{{ t('wizard.ipv6Hint') }}</span>
          </div>
          <a-switch v-model:checked="store.form.ipv6Enabled" :disabled="store.form.mpBgp" />
        </div>
        <template v-if="store.form.ipv6Enabled">
          <a-radio-group v-model:value="store.form.ipv6Mode">
            <a-radio value="link_local">{{ t('wizard.linkLocal') }}</a-radio>
            <a-radio value="global">{{ t('wizard.globalUnicast') }}</a-radio>
          </a-radio-group>
          <a-form-item
            v-if="store.form.ipv6Mode === 'global'"
            :label="t('wizard.ipv6Global')"
            required
            style="margin-top: 12px"
          >
            <a-input v-model:value="store.form.ipv6Address" size="large" />
          </a-form-item>
          <a-form-item v-else :label="t('wizard.ipv6LinkLocal')" required style="margin-top: 12px">
            <a-input v-model:value="store.form.ipv6LinkLocalAddress" size="large" />
          </a-form-item>
        </template>
      </a-form>
    </a-card>

    <a-card class="panel" v-else :title="t('wizard.step3Title')">
      <p class="hint">{{ t('wizard.step3Hint') }}</p>
      <a-row :gutter="16">
        <a-col :xs="24" :md="12">
          <a-card size="small" class="review">
            <p class="eyebrow">{{ t('wizard.yourData') }}</p>
            <a-descriptions :column="1" size="small">
              <a-descriptions-item :label="t('wizard.review.node')">{{ store.form.node }}</a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.contact')">{{ store.form.contact }}</a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.endpoint')">
                <span class="mono">{{ store.form.endpoint }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.publicKey')">
                <span class="mono">{{ store.form.publicKey }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.mtu')">{{ store.form.mtu }}</a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.routeExchange')">
                {{ store.sessionModelLabel() }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.ipv4')">
                <span class="mono">{{ store.form.ipv4Address || t('wizard.review.notUsed') }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.ipv6')">
                <span class="mono">{{ peerAddress }}</span>
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-card size="small" class="review">
            <p class="eyebrow">{{ t('wizard.ourData') }}</p>
            <a-descriptions :column="1" size="small">
              <a-descriptions-item :label="t('wizard.review.endpoint')">
                <span class="mono">{{ node?.peering?.endpoint || t('peer.notConfigured') }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.publicKey')">
                <span class="mono">{{ node?.peering?.publickey || t('peer.notConfigured') }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.listenPort')">
                {{ t('wizard.review.assigned') }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('wizard.review.localAddress')">
                {{ t('wizard.review.generated') }}
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-col>
      </a-row>
    </a-card>

    <div class="actions">
      <a-button @click="back">{{ step > 1 ? t('wizard.back') : t('wizard.cancel') }}</a-button>
      <a-button v-if="step < 3" type="primary" @click="next">{{ t('wizard.continue') }}</a-button>
      <a-button v-else type="primary" :loading="store.saving.value" @click="submit">
        {{ t('wizard.confirm') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.peering-page {
  padding: 32px 24px 64px;
  max-width: 860px;
  margin: 0 auto;
}

.back {
  padding-left: 0;
  margin-bottom: 8px;
}

.heading {
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

.heading h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
}

.subtitle,
.hint {
  color: rgba(0, 0, 0, 0.45);
  margin: 8px 0 0;
}

.steps {
  margin-bottom: 24px;
}

.panel {
  border-radius: 10px;
}

.option-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  margin-bottom: 12px;
}

.option-row b,
.option-row span {
  display: block;
}

.capability {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #91caff;
  border-radius: 8px;
  background: #e6f4ff;
}

.dark .capability {
  border-color: rgba(24, 144, 255, 0.45);
  background: rgba(24, 144, 255, 0.15);
}

.cap-text {
  min-width: 0;
}

.cap-text b,
.cap-text span {
  display: block;
}

.cap-check {
  flex-shrink: 0;
  color: #1890ff;
  font-size: 18px;
}

.review .eyebrow {
  margin-bottom: 8px;
}

.mono {
  font-family: 'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace;
  word-break: break-all;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
}

.dark .subtitle,
.dark .hint {
  color: rgba(255, 255, 255, 0.55);
}
</style>
