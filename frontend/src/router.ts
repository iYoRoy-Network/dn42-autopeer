import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { api } from './common/packetHandler'
import type { Principal } from './common/packetHandler'

const routes: RouteRecordRaw[] = [
  {
    path: '/signin',
    name: 'signin',
    component: () => import('./pages/signin/signin.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'landing',
    component: () => import('./pages/landing/landing.vue'),
  },
  {
    path: '/nodes/:node',
    name: 'node',
    component: () => import('./pages/nodes/nodes.vue'),
  },
  {
    path: '/nodes/:node/peers/new',
    name: 'peer-create',
    component: () => import('./pages/peering/peering.vue'),
  },
  {
    path: '/nodes/:node/peers/:asn/edit',
    name: 'peer-edit',
    component: () => import('./pages/peering/peering.vue'),
  },
  {
    path: '/sessions',
    name: 'sessions',
    component: () => import('./pages/manage/manage.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

let identityPromise: Promise<Principal> | null = null

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  try {
    identityPromise ??= api.currentUser()
    await identityPromise
    return true
  } catch (error) {
    identityPromise = null
    if ((error as { status?: number }).status === 401) {
      return { name: 'signin', query: { redirect: to.fullPath } }
    }
    return true
  }
})

export function resetRouterIdentity(): void {
  identityPromise = null
}

export default router
