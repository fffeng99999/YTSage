/** History API */
import api from './http'

export function listHistory(q) {
  return api.get('/history', { params: q ? { q } : {} }).then((r) => r.data)
}

export function deleteHistory(entryId) {
  return api.delete(`/history/${entryId}`).then((r) => r.data)
}

export function clearHistory() {
  return api.delete('/history').then((r) => r.data)
}
