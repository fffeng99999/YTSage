/**
 * Batch & Channel analysis API (new "批量下载" page).
 * Long per-request timeouts: batch/channel parsing runs yt-dlp
 * subprocesses server-side and can take minutes.
 */
import api from './http'

export function analyzeBatch(payload) {
  return api.post('/analyze/batch', payload, { timeout: 300000 }).then((r) => r.data)
}

export function analyzeChannel(payload) {
  return api.post('/analyze/channel', payload, { timeout: 300000 }).then((r) => r.data)
}

// ---- persistent batches (separate from normal / sync downloads) ----------

export function createBatch(urls, path, name) {
  return api.post('/batch', { urls, path, name }).then((r) => r.data)
}

export function listBatches(limit = 30, offset = 0) {
  return api.get('/batch', { params: { limit, offset } }).then((r) => r.data)
}

export function getBatch(id) {
  return api.get(`/batch/${id}`).then((r) => r.data)
}

export function retryBatch(id) {
  return api.post(`/batch/${id}/retry`).then((r) => r.data)
}

export function cancelBatch(id) {
  return api.post(`/batch/${id}/cancel`).then((r) => r.data)
}

export function deleteBatch(id) {
  return api.delete(`/batch/${id}`).then((r) => r.data)
}

export function listTasks(source, limit = 50, offset = 0) {
  return api.get('/tasks', { params: { source, limit, offset } }).then((r) => r.data)
}
