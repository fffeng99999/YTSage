/**
 * Download store - manages job list via WebSocket + REST fallback.
 * Also routes command_output / updater events to their consumers.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listJobs, activeTasks } from '@/api/download'
import { useSettingsStore } from '@/stores/settings'

export const useDownloadStore = defineStore('download', () => {
  const jobs = ref([])
  const ws = ref(null)
  const connected = ref(false)
  const reconnectTimer = ref(null)
  // Exponential backoff state (module 6.3): 1s -> 2s -> 4s ... capped at 30s
  const reconnectDelay = ref(1000)
  const RECONNECT_MAX = 30000
  let manualClose = false

  // Custom command console (Tools page)
  const commandLines = ref([])
  const commandRunning = ref(false)
  // Latest updater event per component
  const updaterEvents = ref({})
  // Listeners for job_finished (sound/notification)
  const finishListeners = ref([])

  async function fetchJobs() {
    try {
      const data = await listJobs()
      jobs.value = data.jobs || []
    } catch (e) {
      console.error('fetchJobs error:', e)
    }
  }

  /**
   * Resync after page load / WS (re)connect (module 6.3): pull the in-flight
   * snapshot and merge it in. Any locally-known job still marked in-flight but
   * absent from the snapshot finished (or was removed) while we were offline,
   * so fall back to the full list once to reconcile.
   */
  async function fetchActiveJobs() {
    try {
      const data = await activeTasks()
      const snapshot = data.jobs || []
      const ids = new Set(snapshot.map((j) => j.job_id))
      for (const job of snapshot) updateJob({ job })
      const stale = jobs.value.some(
        (j) => ['pending', 'queued', 'running', 'paused'].includes(j.status) && !ids.has(j.job_id)
      )
      if (stale) await fetchJobs()
    } catch (e) {
      console.error('fetchActiveJobs error:', e)
      fetchJobs()
    }
  }

  function updateJob(event) {
    const job = event.job
    if (!job) return
    const idx = jobs.value.findIndex((j) => j.job_id === job.job_id)
    if (idx >= 0) {
      jobs.value[idx] = { ...jobs.value[idx], ...job }
    } else {
      jobs.value.push(job)
    }
  }

  function onFinished(fn) {
    finishListeners.value.push(fn)
  }

  function handleEvent(event) {
    switch (event.type) {
      case 'job_created':
      case 'job_update':
        updateJob(event)
        break
      case 'job_finished': {
        updateJob(event)
        const job = event.job
        if (job && (job.status === 'completed' || job.status === 'error')) {
          finishListeners.value.forEach((fn) => { try { fn(job, event.success) } catch {} })
        }
        break
      }
      case 'job_removed':
        jobs.value = jobs.value.filter((j) => j.job_id !== event.job_id)
        break
      case 'command_output':
        commandRunning.value = true
        commandLines.value.push(event.line)
        if (commandLines.value.length > 2000) commandLines.value.splice(0, 500)
        break
      case 'command_finished':
        commandRunning.value = false
        commandLines.value.push(`[exit ${event.exit_code}]`)
        break
      case 'updater':
        updaterEvents.value = { ...updaterEvents.value, [event.component]: event }
        break
    }
  }

  function clearCommandLog() {
    commandLines.value = []
  }

  function connectWebSocket() {
    if (ws.value) return

    const token = localStorage.getItem('ytsage_token')
    if (!token) return
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/ws?token=${encodeURIComponent(token)}`

    manualClose = false
    try {
      ws.value = new WebSocket(url)

      ws.value.onopen = () => {
        connected.value = true
        reconnectDelay.value = 1000 // reset backoff after a healthy link
        // Resync: refresh may have missed job events while disconnected.
        fetchActiveJobs()
      }

      ws.value.onmessage = (evt) => {
        try {
          handleEvent(JSON.parse(evt.data))
        } catch (e) {
          console.error('WS parse error:', e)
        }
      }

      ws.value.onclose = () => {
        connected.value = false
        ws.value = null
        if (manualClose) return // explicit disconnect: don't auto-reconnect
        if (reconnectTimer.value) clearTimeout(reconnectTimer.value)
        const delay = reconnectDelay.value
        reconnectDelay.value = Math.min(delay * 2, RECONNECT_MAX)
        reconnectTimer.value = setTimeout(connectWebSocket, delay)
      }

      ws.value.onerror = () => {
        ws.value?.close()
      }
    } catch (e) {
      console.error('WS connect error:', e)
    }
  }

  function disconnectWebSocket() {
    manualClose = true
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }
    ws.value?.close()
    ws.value = null
    connected.value = false
  }

  return {
    jobs, connected,
    commandLines, commandRunning, updaterEvents,
    fetchJobs, connectWebSocket, disconnectWebSocket,
    onFinished, clearCommandLog,
  }
})
