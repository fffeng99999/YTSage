<template>
  <div class="sync-logs-page">
    <div class="yts-card">
      <div class="toolbar">
        <el-select v-model="logFile" size="small" style="width: 240px" @change="onFileChange">
          <el-option v-for="f in logOptions" :key="f.name" :label="f.name + (f.compressed ? ' (.zip)' : '')" :value="f.name" :disabled="!f.pickable" />
        </el-select>
        <el-button size="small" :icon="Refresh" @click="loadFiles">{{ t('web.sync.refresh') }}</el-button>
        <div class="spacer" />
        <el-switch v-model="follow" size="small" :active-text="t('logs.follow')" />
        <el-button size="small" @click="togglePause">{{ paused ? t('logs.resume') : t('logs.pause') }}</el-button>
        <el-button size="small" @click="clearLog">{{ t('logs.clear') }}</el-button>
      </div>
      <div ref="logView" class="log-view" v-loading="logLoading">
        <pre v-if="logText">{{ logText }}</pre>
        <el-empty v-else :description="t('logs.empty')" :image-size="60" />
      </div>
      <div class="foot">
        <span>{{ t('logs.files') }}: {{ logFile || '-' }}</span>
        <span v-if="logFileSize != null">· {{ fmtBytes(logFileSize) }}</span>
        <span v-if="paused" class="dim">· {{ t('logs.paused_hint') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Refresh } from '@element-plus/icons-vue'
import { listLogFiles, readLog } from '@/api/logs'

const { t } = useI18n()
const logFile = ref('ytsage.log')
const logText = ref('')
const logOffset = ref(0)
const logFileSize = ref(null)
const follow = ref(true)
const paused = ref(false)
const logLoading = ref(false)
const logView = ref(null)
const logOptions = ref([])
let pollTimer = null
const MAX_LOG_CHARS = 2 * 1024 * 1024

async function loadFiles() {
  try {
    const data = await listLogFiles()
    const files = data.files || []
    logOptions.value = files
    if (!files.some((f) => f.name === logFile.value)) {
      const pickable = files.find((f) => f.pickable)
      logFile.value = pickable ? pickable.name : ''
    }
    if (!logFile.value) resetLog()
  } catch { /* ignore */ }
}

function resetLog() { logText.value = ''; logOffset.value = 0; logFileSize.value = null }
function onFileChange() { resetLog(); poll(false) }

async function poll(append = true) {
  if (!logFile.value) return
  logLoading.value = true
  try {
    const data = await readLog(logFile.value, logOffset.value)
    if (data.rotated) { logText.value = ''; logOffset.value = 0 }
    logFileSize.value = data.size
    if (data.content) {
      if (append) {
        logText.value += data.content
        if (logText.value.length > MAX_LOG_CHARS) logText.value = logText.value.slice(logText.value.length - MAX_LOG_CHARS)
      } else {
        logText.value = data.content
      }
      logOffset.value = data.offset
      if (follow.value) scrollToBottom()
    }
  } catch (e) {
    if (e.response?.status === 404) resetLog()
  } finally {
    logLoading.value = false
  }
}

function scrollToBottom() { nextTick(() => { const el = logView.value; if (el) el.scrollTop = el.scrollHeight }) }
function togglePause() { paused.value = !paused.value }
function clearLog() { resetLog() }
function fmtBytes(b) {
  if (!b) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${units[i]}`
}

onMounted(() => {
  loadFiles()
  poll(false)
  pollTimer = setInterval(() => { if (!paused.value) poll() }, 2000)
})
onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.sync-logs-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.toolbar .spacer { flex: 1; }
.log-view { height: calc(100vh - 260px); min-height: 320px; overflow: auto; background: #0d0d0f; border: 1px solid var(--yts-border); border-radius: 8px; padding: 12px; }
.log-view pre { margin: 0; color: #d4d4d4; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; font-family: Consolas, Monaco, monospace; }
.foot { margin-top: 8px; font-size: 12px; color: var(--yts-text-dim); display: flex; gap: 6px; }
.foot .dim { opacity: 0.7; }
</style>
