<template>
  <section class="page-heading admin-heading">
    <div>
      <p class="eyebrow">ADMINISTRATION</p>
      <h1>Network administration</h1>
      <p>Inspect every peering-enabled node and manage peer sessions across the network.</p>
    </div>
    <mdui-button variant="outlined" @click="router.push({ name: 'admin-sessions' })">All peer sessions</mdui-button>
  </section>
  <NodesPage />
</template>
<script setup>
import { useRouter } from 'vue-router'
import NodesPage from '../nodes/NodesPage.vue'
const router = useRouter()
</script>