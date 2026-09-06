/**
 * Download store - manages job list via WebSocket + REST fallback.
 * Also routes command_output / updater events to their consumers.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listJobs } from '@/api/download'
import { useSettingsStore } from '@/stores/settings'

export const useDownloadStore = defineStore('download', () => {
  const jobs = ref([])
  const ws = ref(null)
  const connected = ref(false)
  const reconnectTimer = ref(null)

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

    try {
      ws.value = new WebSocket(url)

      ws.value.onopen = () => {
        connected.value = true
        fetchJobs()
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
        if (reconnectTimer.value) clearTimeout(reconnectTimer.value)
        reconnectTimer.value = setTimeout(connectWebSocket, 3000)
      }

      ws.value.onerror = () => {
        ws.value?.close()
      }
    } catch (e) {
      console.error('WS connect error:', e)
    }
  }

  function disconnectWebSocket() {
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
