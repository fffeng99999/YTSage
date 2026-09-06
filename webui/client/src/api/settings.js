/**
 * Settings API
 */
import api from './http'

export function getSettings() {
  return api.get('/settings').then((r) => r.data)
}

export function updateSettings(data) {
  return api.post('/settings', data).then((r) => r.data)
}

export function getHealth() {
  return api.get('/health').then((r) => r.data)
}
