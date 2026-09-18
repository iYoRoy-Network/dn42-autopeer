<script setup>
import { onMounted } from 'vue'
import LayoutHeader from './components/LayoutHeader.vue'
import LayoutContent from './components/LayoutContent.vue'
import LayoutFooter from './components/LayoutFooter.vue'
import LoginPage from './pages/LoginPage.vue'
import { useAutopeer } from './state/autopeer'

const s = useAutopeer()
onMounted(() => s.bootstrap())
</script>
<template>
  <main class="app-shell">
    <section v-if="s.loading.value" class="loading-screen" aria-live="polite">
      <mdui-circular-progress aria-label="Loading autopeer" />
      <p>Loading autopeer control plane…</p>
    </section>
    <LoginPage v-else-if="!s.currentUser.value" />
    <template v-else>
      <LayoutHeader />
      <LayoutContent />
      <LayoutFooter />
    </template>
  </main>
</template>