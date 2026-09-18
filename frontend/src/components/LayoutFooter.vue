<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { themeName } from '../common/helper'
import config from '../config'

const { t } = useI18n()
const currentYear = new Date().getFullYear()
</script>

<template>
  <a-layout-footer id="footer" :class="themeName">
    <p class="mono">{{ t('footer.tagline') }}</p>
    <p class="mono credit">
      {{ t('footer.credit') }} ·
      <a :href="config.credit.url" target="_blank" rel="noopener">{{ config.credit.name }}</a>
      ({{ config.credit.license }})
    </p>
    <p class="mono">
      © {{ currentYear }} ·
      <a href="https://dn42.dev" target="_blank" rel="noopener">{{ t('footer.participant') }}</a>
      · iyoroynet autopeer (Frontend v{{ config.version }})
    </p>
  </a-layout-footer>
</template>

<style scoped>
#footer {
  font-size: 0.875rem;
  text-align: center;
  width: 100%;
  padding: 2.5rem;
}

#footer.light {
  background-color: #f8f8f8;
  color: #6c757d;
}

#footer.dark {
  background-color: #111;
  color: #87929c;
}

#footer .mono {
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono',
    Consolas, 'Courier New', monospace;
  font-size: 0.75rem;
  margin: 0.25rem 0 0;
}

#footer a {
  font-weight: 600;
  color: #495057;
}

#footer a:hover {
  color: #007bff;
  text-decoration: underline;
}

#footer.dark a {
  color: #adb5bd;
}
</style>
