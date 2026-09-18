import { computed, reactive, ref } from 'vue'
import { api, setDevAsn } from '../api'

const currentUser = ref(null)
const nodes = ref([])
const sessions = ref([])
const statuses = ref([])
const loading = ref(false)
const loadingStatus = ref(false)
const error = ref('')
const notice = ref('')
const pendingJob = ref(null)
const saving = ref(false)
const activeSession = ref(null)
const wizardStep = ref(1)
const form = reactive({ mode: 'create', node: '', asn: '', contact: '', publicKey: '', endpoint: '', mtu: 1420, mpBgp: false, ipv4Enabled: true, ipv6Enabled: true, ipv6Mode: 'link_local', ipv4Address: '', ipv6Address: '', ipv6LinkLocalAddress: '' })
let pollTimer
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const statusByPeer = computed(() => new Map(statuses.value.map(s => [`${s.node}:${s.asn}`, s])))
const statusForSession = s => statusByPeer.value.get(`${s.node.id}:${s.peer.asn}`)
const sessionCount = computed(() => sessions.value.length)
const onlineSessionCount = computed(() => sessions.value.filter(s => statusForSession(s)?.bgp?.up).length)
const totalReceived = computed(() => sessions.value.reduce((n,s) => n + Number(statusForSession(s)?.wireguard?.rx_bytes || 0), 0))
const totalTransmitted = computed(() => sessions.value.reduce((n,s) => n + Number(statusForSession(s)?.wireguard?.tx_bytes || 0), 0))
const totalImportedRoutes = computed(() => sessions.value.reduce((n,s) => n + Number(statusForSession(s)?.bgp?.routes_imported || 0), 0))
const totalExportedRoutes = computed(() => sessions.value.reduce((n,s) => n + Number(statusForSession(s)?.bgp?.routes_exported || 0), 0))
const formatBytes = value => { if (value == null || !Number.isFinite(Number(value))) return '—'; const units=['B','KiB','MiB','GiB','TiB']; let n=Number(value), i=0; while(Math.abs(n)>=1024&&i<units.length-1){n/=1024;i++} return `${n.toLocaleString(undefined,{maximumFractionDigits:1})} ${units[i]}` }
const formatRate = value => value == null ? '—' : `${formatBytes(value)}/s`
function resetForm(session = null, node = null) { const p=session?.peer; form.mode=p?'edit':'create'; form.node=session?.node.id??node?.id??''; form.asn=p?String(p.asn):String(isAdmin.value?'':(currentUser.value?.asn??'')); form.contact=p?.description??''; form.publicKey=p?.wireguard_public_key??''; form.endpoint=p?.wireguard_endpoint??''; form.mtu=p?.mtu??1420; const b=p?.bgp??{}; form.mpBgp=b.mp_bgp??Boolean(p?.extended_next_hop); form.ipv4Enabled=b.ipv4_enabled??p?.address_families?.includes('ipv4')??true; form.ipv6Enabled=b.ipv6_enabled??p?.address_families?.includes('ipv6')??true; form.ipv6Mode=b.ipv6_mode??(p?.bgp_transport?.mode==='ipv6'?'global':'link_local'); form.ipv4Address=b.ipv4_address??(p?.bgp_transport?.mode==='ipv4'?p.bgp_transport.remote_address:''); form.ipv6Address=b.ipv6_address??(p?.bgp_transport?.mode==='ipv6'?p.bgp_transport.remote_address:''); form.ipv6LinkLocalAddress=b.ipv6_link_local_address??(p?.bgp_transport?.mode==='ipv6_link_local'?p.bgp_transport.remote_address:''); wizardStep.value=1 }
async function loadSessions(){ if(!currentUser.value)return; const list=isAdmin.value?api.adminPeers:api.peers; sessions.value=(await Promise.all(nodes.value.map(async node=>{try{return (await list(node.id)).map(peer=>({node,peer}))}catch{return []}}))).flat() }
async function loadStatus(){ if(!currentUser.value)return; loadingStatus.value=true; try{statuses.value=isAdmin.value?(await Promise.all(sessions.value.map(s=>api.adminStatus(s.peer.asn)))).flat():await api.status()}catch(e){statuses.value=[];notice.value=e.message}finally{loadingStatus.value=false} }
async function bootstrap(){ loading.value=true; error.value=''; try{currentUser.value=await api.currentUser(); nodes.value=isAdmin.value?await api.adminNodes():await api.nodes(); await loadSessions(); await loadStatus()}catch(e){if(e.status===401){currentUser.value=null;nodes.value=[];sessions.value=[];statuses.value=[]}else error.value=e.message}finally{loading.value=false} }
function openCreate(node){resetForm(null,node)}
function openEdit(s){activeSession.value=s;resetForm(s)}
function setMpBgp(v){form.mpBgp=v;if(v){form.ipv4Enabled=false;form.ipv6Enabled=true}}
function validate(step){if(step===1&&!form.contact.trim())return 'Contact information is required.';if(step===2&&(!form.publicKey.trim()||!form.endpoint.trim()))return 'WireGuard connection details are required.';if(step===2&&!form.mpBgp&&!form.ipv4Enabled&&!form.ipv6Enabled)return 'Enable IPv4, IPv6, or MP-BGP.';if(step===2&&form.ipv4Enabled&&!form.mpBgp&&!form.ipv4Address.trim())return 'An IPv4 address is required.';if(step===2&&form.ipv6Enabled&&form.ipv6Mode==='global'&&!form.ipv6Address.trim())return 'An IPv6 global address is required.';if(step===2&&form.ipv6Enabled&&form.ipv6Mode==='link_local'&&!form.ipv6LinkLocalAddress.trim())return 'An IPv6 link-local address is required.'}
function nextWizardStep(){const e=validate(wizardStep.value);if(e){error.value=e;return false}error.value='';wizardStep.value++;return true}
function payload(){return {contact:form.contact,wireguard:{public_key:form.publicKey,endpoint:form.endpoint,mtu:Number(form.mtu)},bgp:{mp_bgp:form.mpBgp,ipv4_enabled:form.ipv4Enabled,ipv6_enabled:form.ipv6Enabled,ipv6_mode:form.ipv6Mode,ipv4_address:form.ipv4Address||null,ipv6_address:form.ipv6Address||null,ipv6_link_local_address:form.ipv6LinkLocalAddress||null}}}
function watchJob(job){pendingJob.value=job;clearInterval(pollTimer);pollTimer=setInterval(async()=>{try{pendingJob.value=await api.job(job.id);if(['succeeded','failed'].includes(pendingJob.value.status)){clearInterval(pollTimer);if(pendingJob.value.status==='succeeded'){notice.value=`Job ${job.id} completed.`;await loadSessions();await loadStatus()}else error.value=pendingJob.value.error||'Job failed.'}}catch(e){clearInterval(pollTimer);error.value=e.message}},1500)}
async function saveSession(){const e=validate(1)||validate(2);if(e){error.value=e;return}if(isAdmin.value&&form.mode==='create'&&!form.asn.trim()){error.value='Peer ASN is required.';return} saving.value=true;try{const p=payload();const job=form.mode==='create'?(isAdmin.value?await api.createAdminPeer(form.node,Number(form.asn),p):await api.createPeer(form.node,p)):(isAdmin.value?await api.patchAdminPeer(form.node,Number(form.asn),p):await api.patchPeer(form.node,Number(form.asn),p));notice.value=`Queued ${job.kind.replaceAll('_',' ')}.`;watchJob(job)}catch(e){error.value=e.message}finally{saving.value=false}}
async function deleteSession(){if(!activeSession.value)return;saving.value=true;try{const {node,peer}=activeSession.value;const job=isAdmin.value?await api.deleteAdminPeer(node.id,peer.asn):await api.deletePeer(node.id,peer.asn);notice.value=`Queued removal for AS${peer.asn}.`;watchJob(job);activeSession.value=null}catch(e){error.value=e.message}finally{saving.value=false}}
export function useAutopeer(){return {currentUser,nodes,sessions,statuses,loading,loadingStatus,error,notice,pendingJob,saving,activeSession,wizardStep,form,isAdmin,sessionCount,onlineSessionCount,totalReceived,totalTransmitted,totalImportedRoutes,totalExportedRoutes,statusForSession,formatBytes,formatRate,bootstrap,loadStatus,loadSessions,openCreate,openEdit,resetForm,setMpBgp,nextWizardStep,saveSession,deleteSession,clearError:()=>error.value='',clearNotice:()=>notice.value='',logout:async()=>{try{await api.logout()}finally{localStorage.removeItem('autopeer-dev-asn');setDevAsn('');currentUser.value=null}},applyDevIdentity:async asn=>{localStorage.setItem('autopeer-dev-asn',asn);setDevAsn(asn);await bootstrap()}}}
setDevAsn(localStorage.getItem('autopeer-dev-asn')||'')
