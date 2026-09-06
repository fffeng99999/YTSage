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
