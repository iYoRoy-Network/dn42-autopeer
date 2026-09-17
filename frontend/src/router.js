import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'

const routes = [
  { path: '/login', name: 'login', meta: { public: true } },
  { path: '/', name: 'home', meta: { area: 'user' } },
  { path: '/nodes/:node', name: 'node', meta: { area: 'user' } },
  { path: '/nodes/:node/peers/new', name: 'peer-create', meta: { area: 'user' } },
  { path: '/nodes/:node/peers/:asn/edit', name: 'peer-edit', meta: { area: 'user' } },
  { path: '/nodes/:node/peers/:asn', name: 'peer', meta: { area: 'user' } },
  { path: '/sessions', name: 'sessions', meta: { area: 'user' } },
  { path: '/admin', name: 'admin-home', meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node', name: 'admin-node', meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/new', name: 'admin-peer-create', meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/:asn/edit', name: 'admin-peer-edit', meta: { area: 'admin', admin: true } },
  { path: '/admin/nodes/:node/peers/:asn', name: 'admin-peer', meta: { area: 'admin', admin: true } },
  { path: '/admin/sessions', name: 'admin-sessions', meta: { area: 'admin', admin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(), routes })

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
