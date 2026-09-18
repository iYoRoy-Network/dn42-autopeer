<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoginOutlined, SafetyOutlined } from '@ant-design/icons-vue'
import { useAutopeer } from '@/store'

const { t } = useI18n()
const store = useAutopeer()

const asn = ref('')
const dev = import.meta.env.MODE === 'development'
</script>

<template>
  <div class="signin-page">
    <div class="brand">
      <div class="brand-mark">↔</div>
      <div>
        <p class="eyebrow">{{ t('signin.eyebrow') }}</p>
        <h1>iyoroynet autopeer</h1>
        <p class="subtitle">{{ t('signin.subtitle') }}</p>
      </div>
    </div>

    <a-card class="signin-card">
      <h2>{{ t('signin.signIn') }}</h2>
      <p class="hint">{{ t('signin.hint') }}</p>

      <a-button type="primary" size="large" block href="/api/v1/auth/login">
        <login-outlined />
        {{ t('signin.oauth') }}
      </a-button>

      <template v-if="dev">
        <a-divider />
        <p class="hint">
          <safety-outlined />
          {{ t('signin.dev') }}
        </p>
        <a-input
          v-model:value="asn"
          type="number"
          size="large"
          :placeholder="t('signin.devAsn')"
          style="margin-bottom: 12px"
        />
        <a-button block @click="store.applyDevIdentity(asn)">{{ t('signin.useDev') }}</a-button>
      </template>
    </a-card>
  </div>
</template>

<style scoped>
.signin-page {
  min-height: calc(100vh - 65px);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 400px);
  gap: 48px;
  align-items: center;
  max-width: 1000px;
  margin: 0 auto;
  padding: 48px 24px;
}

.brand {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border-radius: 14px;
  background: #1890ff;
  color: #fff;
  font-weight: 800;
  font-size: 28px;
}

.eyebrow {
  margin: 0 0 4px;
  color: #1890ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.brand h1 {
  margin: 0;
  font-size: 44px;
  line-height: 1.05;
  letter-spacing: -0.03em;
}

.subtitle {
  color: rgba(0, 0, 0, 0.55);
  margin: 12px 0 0;
  line-height: 1.6;
  max-width: 460px;
}

.signin-card {
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(31, 49, 42, 0.08);
}

.signin-card h2 {
  margin: 0 0 8px;
}

.hint {
  color: rgba(0, 0, 0, 0.45);
  line-height: 1.6;
  margin: 0 0 20px;
}

@media (max-width: 768px) {
  .signin-page {
    grid-template-columns: 1fr;
    gap: 32px;
  }
}

.dark .subtitle,
.dark .hint {
  color: rgba(255, 255, 255, 0.55);
}
</style>
