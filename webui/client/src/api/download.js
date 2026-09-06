/**
 * Analysis & Download API
 */
import api from './http'

export function analyzeUrl(payload) {
  return api.post('/analyze', payload).then((r) => r.data)
}

export function startDownload(payload) {
  return api.post('/download', payload).then((r) => r.data)
}

export function listJobs() {
  return api.get('/jobs').then((r) => r.data)
}

export function getJob(jobId) {
  return api.get(`/jobs/${jobId}`).then((r) => r.data)
}

export function cancelJob(jobId) {
  return api.post(`/jobs/${jobId}/cancel`).then((r) => r.data)
}

export function pauseJob(jobId) {
  return api.post(`/jobs/${jobId}/pause`).then((r) => r.data)
}

export function resumeJob(jobId) {
  return api.post(`/jobs/${jobId}/resume`).then((r) => r.data)
}

export function removeJob(jobId) {
  return api.delete(`/jobs/${jobId}`).then((r) => r.data)
}
