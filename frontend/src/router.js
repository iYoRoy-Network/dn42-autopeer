import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'

const lazy = (path) => () => import(path)

const routes = [
  { path: '/login', name: 'login', component: lazy('./pages/LoginPage.vue'), meta: { public: true } },
  { path: '/', name: 'home', component: lazy('./pages/home/HomePage.vue'), meta: { area: 'user' } },
  { path: '/nodes/:node', name: 'node', component: lazy('./pages/nodes/NodePage.vue'), meta: { area: 'user' } },
  { path: '/nodes/:node/peers/new', name: 'peer-create', component: lazy('./pages/peers/PeerWizardPage.vue'), meta: { area: 'user' } },
  { path: '/nodes/:node/peers/:asn/edit', name: 'peer-edit', component: lazy('./pages/peers/PeerWizardPage.vue'), meta: { area: 'user' } },
  { path: '/nodes/:node/peers/:asn', name: 'peer', component: lazy('./pages/peers/PeerPage.vue'), meta: { area: 'user' } },
  { path: '/sessions', name: 'sessions', component: lazy('./pages/sessions/SessionsPage.vue'), meta: { area: 'user' } },
  { path: '/admin', name: 'admin-home', component: lazy('./pages/admin/AdminPage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node', name: 'admin-node', component: lazy('./pages/nodes/NodePage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/new', name: 'admin-peer-create', component: lazy('./pages/peers/PeerWizardPage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/:asn/edit', name: 'admin-peer-edit', component: lazy('./pages/peers/PeerWizardPage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/:asn', name: 'admin-peer', component: lazy('./pages/peers/PeerPage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/admin/sessions', name: 'admin-sessions', component: lazy('./pages/sessions/SessionsPage.vue'), meta: { area: 'admin', admin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0, behavior: 'smooth' }
  },
})

let identityPromise
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  try {
    identityPromise ??= api.currentUser()
    const user = await identityPromise
    if (to.meta.admin && user.role !== 'admin') return { name: 'home' }
    return true
  } catch (error) {
    identityPromise = null
    if (error.status === 401) return { name: 'login', query: { redirect: to.fullPath } }
    return true
  }
})

export function resetRouterIdentity() {
  identityPromise = null
}

export default router