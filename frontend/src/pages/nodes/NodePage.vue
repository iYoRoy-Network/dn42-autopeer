<script setup>
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAutopeer } from '../../state/autopeer'
const s=useAutopeer(), route=useRoute(), router=useRouter()
const node=computed(()=>s.nodes.value.find(n=>n.id===route.params.node))
const nodeSessions=computed(()=>s.sessions.value.filter(x=>x.node.id===route.params.node))
onMounted(async()=>{if(!s.currentUser.value) await s.bootstrap()})
function create(){if(node.value){s.openCreate(node.value);router.push({name:s.isAdmin.value?'admin-peer-create':'peer-create',params:{node:node.value.id}})}}
function details(session){router.push({name:s.isAdmin.value?'admin-peer':'peer',params:{node:session.node.id,asn:session.peer.asn}})}
</script>
<template>
<section v-if="node" class="node-detail-page">
  <mdui-button variant="text" @click="router.push({name:s.isAdmin.value?'admin-home':'home'})">← Back to nodes</mdui-button>
  <section class="page-heading"><div><p class="eyebrow">{{node.id}}</p><h1>{{node.peering?.display_name||node.name}}</h1><p>{{node.peering?.subtitle||'DN42 WireGuard peering node'}}</p></div><mdui-button variant="filled" :disabled="!node.peering_enabled" @click="create">Start peering</mdui-button></section>
  <section class="detail-metrics"><article><span>Peers</span><strong>{{node.peer_count??nodeSessions.length}}</strong></article><article><span>Online</span><strong>{{node.online_peer_count??'—'}}</strong></article><article><span>Protocol stack</span><strong>{{node.peering?.protocol_stack||'Dual stack'}}</strong></article><article><span>Received</span><strong>{{s.formatBytes(node.runtime_metrics?.rx_bytes)}}</strong></article><article><span>Transmitted</span><strong>{{s.formatBytes(node.runtime_metrics?.tx_bytes)}}</strong></article></section>
  <section class="detail-panel"><h2>Peer sessions</h2><div v-if="nodeSessions.length" class="peering-rows"><article v-for="session in nodeSessions" :key="session.peer.asn" class="peering-row"><div class="peering-node"><span class="node-avatar">AS</span><div><strong>AS{{session.peer.asn}}</strong><span>{{session.peer.description}}</span></div></div><div class="peering-health"><strong :class="s.statusForSession(session)?.bgp?.up?'state-good':'state-unknown'"><span class="state-dot"/>{{s.statusForSession(session)?.bgp?.up?'Established':'Status unavailable'}}</strong><div class="health-lines"><span>{{session.peer.bgp_transport?.mode?.replaceAll('_',' ')}}</span><span>{{session.peer.address_families?.join(' + ')}}</span></div></div><mdui-button variant="outlined" @click="details(session)">View details</mdui-button></article></div><section v-else class="empty-state"><h2>No sessions on this node</h2><p>Create the first peering session to get started.</p><mdui-button variant="filled" @click="create">Start peering</mdui-button></section></section>
</section><section v-else class="empty-state"><h2>Node not found</h2></section>
</template>