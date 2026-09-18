<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { theme as antTheme } from 'ant-design-vue'
import { BulbOutlined, BulbFilled } from '@ant-design/icons-vue'
import LayoutHeader from './components/LayoutHeader.vue'
import LayoutContent from './components/LayoutContent.vue'
import LayoutFooter from './components/LayoutFooter.vue'
import { applyTheme, themeName, isValidTheme, THEME_STORAGE_KEY } from './common/helper'
import type { ThemeName } from './common/helper'
import { locale, setLocale, SupportedLocales } from './i18n/i18n'
import type { SupportedLocale } from './i18n/i18n'

const vueI18n = useI18n()
const antdLocale = ref<unknown>(null)

const stopWatchLocale = watch(
  () => locale.value,
  (newLocale: SupportedLocale) => {
    vueI18n.locale.value = newLocale
  },
)

onMounted(async () => {
  let resolvedTheme: ThemeName = 'light'
  try {
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY)
    if (isValidTheme(storedTheme)) {
      resolvedTheme = storedTheme
    } else {
      resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
  } catch (error) {
    console.warn('Failed to resolve theme preference, defaulting to light', error)
  }
  applyTheme(resolvedTheme, true)

  let targetLocale: SupportedLocale = 'en_US'
  try {
    const cachedLocale = localStorage.getItem('locale')
    if (cachedLocale && SupportedLocales.includes(cachedLocale as SupportedLocale)) {
      targetLocale = cachedLocale as SupportedLocale
    } else if (navigator.language?.toLowerCase().startsWith('zh')) {
      targetLocale = 'zh_CN'
    }
  } catch (error) {
    console.warn('Failed to resolve locale, defaulting to en_US', error)
  }
  antdLocale.value = await setLocale(targetLocale)

  // Remove the initial loading screen once the app is ready.
  setTimeout(() => {
    const loadingEl = document.getElementById('initial-loading')
    if (loadingEl) {
      loadingEl.classList.add('fade-out')
      setTimeout(() => loadingEl.remove(), 500)
    }
  }, 100)
})

onUnmounted(() => {
  stopWatchLocale()
})

const themeTrigger = computed(() => themeName.value === 'light')
const changeTheme = () => applyTheme(themeTrigger.value ? 'dark' : 'light', true)
</script>

<template>
  <a-config-provider
    :locale="antdLocale"
    :theme="{ algorithm: themeName === 'dark' ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }"
  >
    <a-layout>
      <layout-header />
      <layout-content />
      <layout-footer />
      <a-float-button-group shape="circle" :style="{ right: '24px' }">
        <a-float-button @click="changeTheme">
          <template #icon>
            <bulb-outlined v-if="themeTrigger" />
            <bulb-filled v-else />
          </template>
        </a-float-button>
        <a-back-top :visibility-height="0" />
      </a-float-button-group>
    </a-layout>
  </a-config-provider>
</template>

<style>
html,
#app {
  width: 100%;
  height: 100%;
  user-select: none;
}

body {
  margin: 0;
}

* {
  box-sizing: border-box;
}
</style>
