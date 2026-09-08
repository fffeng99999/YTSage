/** History API */
import api from './http'

export function listHistory(q) {
  return api.get('/history', { params: q ? { q } : {} }).then((r) => r.data)
}

/** Paged query (module 6.1): backend uses SQLite LIMIT/OFFSET. */
export function listHistoryPage(page, limit, keyword) {
  const params = { page, limit }
  if (keyword) params.keyword = keyword
  return api.get('/history', { params }).then((r) => r.data)
}

export function deleteHistory(entryId) {
  return api.delete(`/history/${entryId}`).then((r) => r.data)
}

/** Multi-select history delete: batch-remove many entries in one call. */
export function deleteHistoryBatch(ids) {
  return api.post('/history/batch-delete', { ids }).then((r) => r.data)
}

export function clearHistory() {
  return api.delete('/history').then((r) => r.data)
}
