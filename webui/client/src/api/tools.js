/** Custom command + playlist export API */
import api from './http'

export function runCommand(command, url, path) {
  return api.post('/command/run', { command, url, path }).then((r) => r.data)
}
export function cancelCommand(execId) {
  return api.post(`/command/${execId}/cancel`).then((r) => r.data)
}

/** Trigger browser download of a playlist export. */
export async function exportPlaylist(analysisId, format, title) {
  const resp = await api.post('/playlist/export', { analysis_id: analysisId, format, title }, { responseType: 'blob' })
  const cd = resp.headers['content-disposition'] || ''
  let name = `playlist.${format}`
  const m = cd.match(/filename\*=UTF-8''([^;]+)/)
  if (m) name = decodeURIComponent(m[1])
  const blobUrl = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = name
  a.click()
  URL.revokeObjectURL(blobUrl)
}
