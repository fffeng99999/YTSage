<template>
  <div class="about-page">
    <div class="yts-card">
      <div class="brand-row">
        <el-icon :size="42" color="#c90000"><VideoCamera /></el-icon>
        <div>
          <h2>YTSage</h2>
          <p class="help">{{ t('about.version') }}: {{ health.app_version || '-' }}</p>
          <p class="help">{{ t('about.description') }}</p>
        </div>
      </div>
      <div class="links">
        <a href="https://github.com/oop7/YTSage" target="_blank">{{ t('about.github') }}</a>
        <a href="https://github.com/sponsors/oop7" target="_blank">{{ t('about.sponsor') }}</a>
      </div>
    </div>

    <div class="yts-card">
      <div class="yts-card-title">{{ t('about.system_info') }}</div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="yt-dlp">
          <el-tag size="small" :type="sys.ytdlp?.installed ? 'success' : 'danger'">
            {{ sys.ytdlp?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.ytdlp?.version }}</span>
          <code class="path">{{ sys.ytdlp?.path }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="FFmpeg">
          <el-tag size="small" :type="sys.ffmpeg?.installed ? 'success' : 'danger'">
            {{ sys.ffmpeg?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.ffmpeg?.version }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="Deno">
          <el-tag size="small" :type="sys.deno?.installed ? 'success' : 'danger'">
            {{ sys.deno?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.deno?.version }}</span>
          <el-tag size="small" :type="sys.deno?.integrated_with_ytdlp ? 'success' : 'info'" style="margin-left: 8px">
            {{ sys.deno?.integrated_with_ytdlp ? 'yt-dlp ✓' : 'yt-dlp ✗' }}
          </el-tag>
          <code class="path">{{ sys.deno?.path }}</code>
        </el-descriptions-item>
      </el-descriptions>
      <div class="row">
        <el-button size="small" @click="load" :loading="loading">
          <el-icon><Refresh /></el-icon> {{ t('about.refresh') }}
        </el-button>
        <el-button size="small" @click="openLogs" :title="t('about.logs_tooltip')">📂 Logs</el-button>
      </div>
    </div>

    <!-- Live log viewer (dynamic tail of the official log files) -->
    <div class="yts-card log-card">
      <div class="yts-card-title">{{ t('web.logs.viewer') }}</div>
      <div class="log-toolbar">
        <el-select v-model="logFile" size="small" style="width: 280px" @change="onLogFileChange">
          <el-option
            v-for="f in logOptions"
            :key="f.name"
            :label="f.name"
            :value="f.name"
            :disabled="!f.pickable"
          >
            <span>{{ f.name }}</span>
            <span class="opt-suffix" v-if="f.pickable">{{ fmtBytes(f.size) }}</span>
            <el-tag v-else size="small" type="info" class="opt-tag">{{ t('web.logs.compressed') }}</el-tag>
          </el-option>
        </el-select>
        <span class="log-meta" v-if="logFileSize !== null">
          {{ fmtBytes(logFileSize) }}
        </span>
        <div class="log-spacer" />
        <el-switch
          v-model="follow"
          size="small"
          :active-text="t('web.logs.follow')"
          :title="t('web.logs.follow_hint')"
        />
        <el-button size="small" @click="togglePause">
          {{ paused ? t('web.logs.resume') : t('web.logs.pause') }}
        </el-button>
        <el-button size="small" @click="clearLog">{{ t('web.logs.clear') }}</el-button>
      </div>
      <div class="log-errors" v-if="paused">{{ t('web.logs.paused_hint') }}</div>
      <div v-loading="logLoading" class="log-view" ref="logView">
        <pre v-if="logText" class="log-pre">{{ logText }}</pre>
        <div v-else class="log-empty">{{ t('web.logs.empty') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh, VideoCamera } from '@element-plus/icons-vue'
import { systemStatus, openLogs as apiOpenLogs } from '@/api/system'
import { getHealth } from '@/api/settings'
import { listLogFiles, readLog } from '@/api/logs'
import { errText } from '@/api/http'

const { t } = useI18n()
const sys = ref({})
const health = ref({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    sys.value = await systemStatus()
    health.value = await getHealth()
  } catch (e) {
    ElMessage.error(t('about.refresh_failed') + ': ' + errText(e))
  } finally {
    loading.value = false
  }
}

async function openLogs() {
  try { await apiOpenLogs() } catch (e) { ElMessage.error(errText(e)) }
}

// ---- Live log tail ------------------------------------------------------

const logFile = ref('ytsage.log')
const logText = ref('')
const logOffset = ref(0)
const logFileSize = ref(null)
const follow = ref(true)
const paused = ref(false)
const logLoading = ref(false)
const logView = ref(null)
// Files from /api/logs/files (current .log pickable; .zip archives disabled).
const logOptions = ref([])
let pollTimer = null

// Soft cap: drop old content so a chatty log cannot grow the DOM forever.
const MAX_LOG_CHARS = 2 * 1024 * 1024

async function loadLogFiles() {
  try {
    const data = await listLogFiles()
    const files = data.files || []
    logOptions.value = files
    // Keep the previously selected file when it still exists.
    if (!files.some((f) => f.name === logFile.value)) {
      const pickable = files.find((f) => f.pickable)
      logFile.value = pickable ? pickable.name : ''
    }
    if (!logFile.value) resetLog()
  } catch (e) {
    console.error('listLogFiles failed:', e)
  }
}

function resetLog() {
  logText.value = ''
  logOffset.value = 0
  logFileSize.value = null
}

function onLogFileChange() {
  resetLog()
  poll(false) // immediate fetch for the newly selected file
}

async function poll(append = true) {
  if (!logFile.value) return
  logLoading.value = true
  try {
    const data = await readLog(logFile.value, logOffset.value)
    if (data.rotated) {
      // File was rotated while we tailed it: restart from the top.
      logText.value = ''
      logOffset.value = 0
    }
    logFileSize.value = data.size
    if (data.content) {
      if (append) {
        logText.value += data.content
        // Trim from the front when the buffer grows too large.
        if (logText.value.length > MAX_LOG_CHARS) {
          logText.value = logText.value.slice(logText.value.length - MAX_LOG_CHARS)
        }
      } else {
        logText.value = data.content
      }
      logOffset.value = data.offset
    }
    if (follow.value) scrollToBottom()
  } catch (e) {
    // 404 when the file is gone: reset and let the next poll retry.
    if (e.response?.status === 404) resetLog()
    else console.error('readLog failed:', e)
  } finally {
    logLoading.value = false
  }
}

function scrollToBottom() {
  const el = logView.value
  if (el) el.scrollTop = el.scrollHeight
}

function togglePause() {
  paused.value = !paused.value
}

function clearLog() {
  resetLog()
}

function fmtBytes(b) {
  if (!b) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${units[i]}`
}

onMounted(() => {
  load()
  loadLogFiles()
  poll(false)
  pollTimer = setInterval(() => {
    if (!paused.value) poll()
  }, 2000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.brand-row { display: flex; gap: 16px; align-items: center; }
.brand-row h2 { margin: 0; }
.help { color: var(--yts-text-dim); font-size: 13px; margin: 4px 0; }
.links { margin-top: 12px; display: flex; gap: 16px; }
.links a { color: var(--yts-red); font-size: 13px; }
.ver { margin-left: 12px; }
.path { margin-left: 12px; font-size: 11px; color: var(--yts-text-dim); word-break: break-all; }
.row { margin-top: 12px; display: flex; gap: 10px; }

.log-card { margin-top: 16px; }
.log-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.log-toolbar .log-meta { color: var(--yts-text-dim); font-size: 12px; }
.log-toolbar .log-spacer { flex: 1; }
.opt-suffix { float: right; color: var(--yts-text-dim); font-size: 11px; margin-left: 12px; }
.opt-tag { float: right; margin-left: 12px; }
.log-errors { color: var(--yts-warn, #e6a23c); font-size: 12px; margin-bottom: 6px; }
.log-view {
  height: 320px;
  overflow: auto;
  background: #0d1117;
  border: 1px solid #2d333b;
  border-radius: 6px;
  padding: 10px;
  font-family: Consolas, Menlo, 'Courier New', monospace;
}
.log-pre {
  margin: 0;
  color: #c9d1d9;
  font-size: 11.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-empty { color: #6e7681; font-size: 12px; }
</style>