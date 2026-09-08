/** Log viewer API (About page live log tail) */
import api from './http'

export function listLogFiles() {
  return api.get('/logs/files').then((r) => r.data)
}

export function readLog(name, offset = 0) {
  return api.get('/logs/read', { params: { name, offset } }).then((r) => r.data)
}