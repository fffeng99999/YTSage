import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import axios from 'axios'

let setupStateCache = null

export async function fetchSetupState(force = false) {
  if (setupStateCache && !force) return setupStateCache
  try {
    const { data } = await axios.get('/api/setup/state', { timeout: 10000 })
    setupStateCache = data
  } catch {
    setupStateCache = { setup_complete: true, config_mode: 'standalone' }
  }
  return setupStateCache
}

const routes = [
  {
    path: '/setup',
    name: 'Setup',
    component: () => import('@/views/Setup.vue'),
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'jobs', name: 'Jobs', component: () => import('@/views/Jobs.vue') },
      { path: 'history', name: 'History', component: () => import('@/views/History.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue') },
      { path: 'tools', name: 'Tools', component: () => import('@/views/Tools.vue') },
      { path: 'updater', name: 'Updater', component: () => import('@/views/Updater.vue') },
      { path: 'about', name: 'About', component: () => import('@/views/About.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // First-run: force the setup wizard
  if (localStorage.getItem('ytsage_setup_done') !== '1') {
    const state = await fetchSetupState()
    if (!state.setup_complete && to.name !== 'Setup') {
      return { path: '/setup' }
    }
    if (state.setup_complete) localStorage.setItem('ytsage_setup_done', '1')
  }

  if (to.name === 'Setup') return

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }
})

export default router
