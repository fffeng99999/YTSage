import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
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

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && authStore.isAuthenticated) {
    return { path: '/' }
  }
})

export default router
