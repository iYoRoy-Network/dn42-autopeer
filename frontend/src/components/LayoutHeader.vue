<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAutopeer } from '../state/autopeer'
const router=useRouter(); const route=useRoute(); const state=useAutopeer()
const admin=computed(()=>state.isAdmin.value)
const active=computed(()=>route.name?.includes('sessions')?'sessions':route.meta.area==='admin'?'admin':'nodes')
async function logout(){await state.logout();router.push({name:'login'})}
</script>
<template><header class="app-header"><a class="wordmark" href="/" @click.prevent="router.push({name:admin?'admin-home':'home'})"><span class="wordmark-mark">↔</span><span>iyoroynet <b>autopeer</b></span></a><nav class="header-tabs" aria-label="Primary sections"><span v-if="admin" class="admin-context">Administrator</span><button :class="{active:active==='nodes'}" @click="router.push({name:admin?'admin-home':'home'})">{{admin?'All nodes':'All nodes'}} <span>{{state.nodes.value.length}}</span></button><button :class="{active:active==='sessions'}" @click="router.push({name:admin?'admin-sessions':'sessions'})">{{admin?'All sessions':'My sessions'}} <span>{{state.sessionCount.value}}</span></button></nav><div class="identity"><div class="identity-avatar">{{state.currentUser.value?.display_name?.slice(0,1) || 'A'}}</div><div><strong>{{state.currentUser.value?.display_name || `AS${state.currentUser.value?.asn}`}}</strong><span>AS{{state.currentUser.value?.asn}} · {{state.currentUser.value?.role}}</span></div><mdui-button variant="text" @click="logout">Sign out</mdui-button></div></header></template>