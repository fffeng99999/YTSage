/**
 * Auth store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('ytsage_token') || '')

  const isAuthenticated = computed(() => !!token.value)

  async function login(password) {
    const data = await apiLogin(password)
    token.value = data.token
    localStorage.setItem('ytsage_token', data.token)
    return data
  }

  function logout() {
    token.value = ''
    localStorage.removeItem('ytsage_token')
  }

  return { token, isAuthenticated, login, logout }
})
