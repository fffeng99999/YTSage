/** System API: status, reveal, open-folder, logs, cookies, sound */
import api from './http'

export function systemStatus() {
  return api.get('/system/status').then((r) => r.data)
}
export function revealPath(path) {
  return api.post('/system/reveal', { path }).then((r) => r.data)
}
export function openFolder(path) {
  return api.post('/system/open-folder', { path }).then((r) => r.data)
}
export function openLogs() {
  return api.post('/system/open-logs').then((r) => r.data)
}
export function cookiesStatus() {
  return api.get('/cookies/status').then((r) => r.data)
}
export function cookiesContent() {
  return api.get('/cookies/content').then((r) => r.data)
}
export function applyCookies(payload) {
  return api.post('/cookies/apply', payload).then((r) => r.data)
}
export function clearCookies() {
  return api.post('/cookies/clear').then((r) => r.data)
}
