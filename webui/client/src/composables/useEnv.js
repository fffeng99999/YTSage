/**
 * Runtime environment detection (module 6.2).
 *
 * Local  = the page is served from the same machine as the backend
 *          (localhost / 127.0.0.1 / ::1). "Reveal in folder" makes sense.
 * Remote = LAN / NAS / VPS access. Opening the *server-side* explorer is
 *          useless and confusing, so reveal switches to a direct browser
 *          download (/api/download-file) instead.
 */
const LOOPBACK = new Set(['localhost', '127.0.0.1', '::1', '[::1]', ''])

export function isLocalHost(hostname) {
  const h = (hostname ?? window.location.hostname).toLowerCase()
  return LOOPBACK.has(h)
}

export function useEnv() {
  const local = isLocalHost()
  return {
    local,
    remote: !local,
    /** Direct-download URL for a server-side file (works from any host). */
    fileDownloadUrl(filePath) {
      const token = localStorage.getItem('ytsage_token') || ''
      return `/api/download-file?path=${encodeURIComponent(filePath)}&token=${encodeURIComponent(token)}`
    },
  }
}
