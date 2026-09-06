<template>
  <div class="batch-page">
    <el-tabs v-model="activeTab" class="yts-card batch-tabs">
      <!-- ================= Batch download ================= -->
      <el-tab-pane :label="t('web.batch.tab')" name="batch">
        <div class="yts-card">
          <el-input
            v-model="urlsText"
            type="textarea"
            :rows="6"
            :placeholder="t('web.batch.placeholder')"
            :disabled="batchParsing"
          />
          <div class="action-row">
            <el-button @click="pasteUrls" :disabled="batchParsing">{{ t('buttons.paste_url') }}</el-button>
            <el-button type="danger" :loading="batchParsing" @click="doBatchParse">
              {{ t('web.batch.parse') }}
            </el-button>
            <span class="hint">{{ t('web.batch.hint', { max: 50 }) }}</span>
          </div>
        </div>

        <div v-if="batchRows.length" class="yts-card">
          <div class="action-row" style="margin-top:0">
            <el-select v-model="qualityIdx" style="width: 200px">
              <el-option
                v-for="(p, i) in qualityOptions"
                :key="i"
                :label="p.quality"
                :value="i"
              />
            </el-select>
            <el-input v-model="downloadPath" style="flex:1; min-width: 220px" :placeholder="t('settings.download_path')" />
            <span class="hint">{{ t('web.batch.concurrency') }}</span>
            <el-select v-model="concurrency" style="width: 90px">
              <el-option v-for="n in [1, 2, 3, 5]" :key="n" :label="n" :value="n" />
            </el-select>
            <el-button
              type="danger"
              :disabled="!batchSelected.length || !downloadPath || batchPumping"
              :loading="batchPumping"
              @click="startBatchDownload"
            >
              {{ t('web.batch.download_selected', { count: batchSelected.length }) }}
            </el-button>
            <el-button v-if="batchDone > 0" text @click="router.push('/jobs')">{{ t('web.batch.go_to_jobs') }}</el-button>
          </div>

          <el-table
            :data="batchRows"
            max-height="480"
            row-key="url"
            @selection-change="(rows) => (batchSelected = rows)"
            style="margin-top: 10px"
          >
            <el-table-column type="selection" width="42" :selectable="(r) => r.ok && !r.dl_status" />
            <el-table-column :label="t('web.batch.col_video')" min-width="320">
              <template #default="{ row }">
                <div class="cell-video">
                  <img
                    v-if="row.ok && row.summary.thumbnail"
                    :src="thumbUrl(row.summary.thumbnail)"
                    loading="lazy"
                    @error="(e) => (e.target.style.visibility = 'hidden')"
                  />
                  <div v-else class="thumb-ph">{{ row.ok ? '📹' : '⚠️' }}</div>
                  <div class="cell-meta">
                    <div class="cell-title" :title="row.ok ? row.summary.title : row.url">
                      {{ row.ok ? (row.summary.title || row.url) : row.url }}
                    </div>
                    <div class="cell-sub">
                      <span v-if="row.ok && row.summary.channel">{{ row.summary.channel }}</span>
                      <span v-if="row.ok && row.is_playlist"> · {{ t('web.batch.playlist_count', { count: row.summary.count }) }}</span>
                      <span v-else-if="row.ok && row.summary.duration_string"> · {{ row.summary.duration_string }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('web.batch.col_status')" width="200">
              <template #default="{ row }">
                <el-tag v-if="!row.ok" size="small" type="danger">{{ trErr(row.error_key, row.error_params) }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'queued'" size="small" type="info">{{ t('web.batch.queued') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'running'" size="small">{{ t('download.downloading') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'completed'" size="small" type="success">{{ t('download.completed') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'error'" size="small" type="danger">{{ t('web.batch.failed') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'cancelled'" size="small" type="info">{{ t('download.cancelled') }}</el-tag>
                <el-tag v-else size="small" type="success">{{ t('web.batch.parsed_ok') }}</el-tag>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="batchPumping" class="progress-line">
            {{ t('web.batch.progress', { done: batchDone, total: batchTotal }) }}
          </div>
        </div>
      </el-tab-pane>

      <!-- ================= Channel download ================= -->
      <el-tab-pane :label="t('web.channel.tab')" name="channel">
        <div class="yts-card">
          <div class="url-row">
            <el-input
              v-model="channelUrl"
              :placeholder="t('web.channel.url_placeholder')"
              :disabled="channelParsing"
              @keyup.enter="doChannelParse"
            />
            <el-button type="danger" :loading="channelParsing" :disabled="!channelUrl.trim()" @click="doChannelParse">
              {{ t('web.batch.parse') }}
            </el-button>
          </div>
          <div class="action-row">
            <el-radio-group v-model="channelTab">
              <el-radio-button value="videos">{{ t('web.channel.tab_videos') }}</el-radio-button>
              <el-radio-button value="shorts">{{ t('web.channel.tab_shorts') }}</el-radio-button>
              <el-radio-button value="streams">{{ t('web.channel.tab_streams') }}</el-radio-button>
            </el-radio-group>
            <span class="hint">{{ t('web.channel.limit') }}</span>
            <el-select v-model="channelLimit" style="width: 110px">
              <el-option v-for="n in [50, 100, 200, 500]" :key="n" :label="n" :value="n" />
            </el-select>
          </div>
        </div>

        <div v-if="channelResult" class="yts-card">
          <div class="channel-head">
            <span class="channel-title">{{ channelResult.channel_info.title || '-' }}</span>
            <span class="hint">{{ t('web.channel.total', { count: channelResult.total }) }}</span>
          </div>

          <div class="action-row" style="margin-top:6px">
            <el-select v-model="chQualityIdx" style="width: 200px">
              <el-option
                v-for="(p, i) in qualityOptions"
                :key="i"
                :label="p.quality"
                :value="i"
              />
            </el-select>
            <el-input v-model="downloadPath" style="flex:1; min-width: 220px" :placeholder="t('settings.download_path')" />
            <el-button
              type="danger"
              :disabled="!channelSelected.length || !downloadPath || channelJobId"
              @click="startChannelDownload"
            >
              {{ t('web.batch.download_selected', { count: channelSelected.length }) }}
            </el-button>
            <el-button text @click="selectAllChannel">{{ t('web.channel.select_all') }}</el-button>
          </div>

          <el-table
            ref="channelTableRef"
            :data="channelResult.entries"
            max-height="480"
            row-key="index"
            @selection-change="(rows) => (channelSelected = rows)"
            style="margin-top: 10px"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column type="index" width="55" :index="(i) => i + 1" />
            <el-table-column :label="t('web.batch.col_video')" min-width="360">
              <template #default="{ row }">
                <div class="cell-video">
                  <img
                    v-if="row.thumbnail"
                    :src="thumbUrl(row.thumbnail)"
                    loading="lazy"
                    @error="(e) => (e.target.style.visibility = 'hidden')"
                  />
                  <div v-else class="thumb-ph">📹</div>
                  <div class="cell-meta">
                    <div class="cell-title" :title="row.title">{{ row.title || row.id }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('video_info.duration')" width="110">
              <template #default="{ row }">{{ fmtDur(row.duration) }}</template>
            </el-table-column>
          </el-table>

          <div v-if="channelJob" class="progress-line">
            <el-progress
              :percentage="Math.min(100, channelJob.progress || 0)"
              :stroke-width="10"
              :status="chProgressStatus"
              style="flex:1"
            />
            <el-tag size="small">{{ channelJob.status }}</el-tag>
            <el-button v-if="['running', 'paused'].includes(channelJob.status)" size="small" @click="cancelChannelJob">
              {{ t('buttons.cancel') }}
            </el-button>
            <el-button text size="small" @click="router.push('/jobs')">{{ t('web.batch.go_to_jobs') }}</el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { analyzeBatch, analyzeChannel } from '@/api/batch'
import { startDownload, cancelJob } from '@/api/download'
import { errText } from '@/api/http'
import { PLAYLIST_PRESETS } from '@/stores/analysis'
import { useDownloadStore } from '@/stores/download'
import { useSettingsStore } from '@/stores/settings'

const { t, te } = useI18n()
const router = useRouter()
const downloadStore = useDownloadStore()
const settingsStore = useSettingsStore()

const activeTab = ref('batch')
const downloadPath = ref('')

// Quality options: official playlist presets + audio-only
const qualityOptions = computed(() => [
  ...PLAYLIST_PRESETS,
  { quality: t('web.batch.audio_only'), resolution: '-', format_id: null, audio: true },
])

function thumbUrl(u) {
  return `/api/thumbnail?url=${encodeURIComponent(u)}`
}

function trErr(key, params) {
  if (!key) return ''
  return te(key) ? t(key, params || {}) : key
}

function fmtDur(sec) {
  if (sec === null || sec === undefined) return '-'
  sec = Math.round(sec)
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

// Official _condense_indices port (same as stores/analysis.js)
function condenseIndices(indices) {
  if (!indices.length) return null
  const sorted = [...new Set(indices)].sort((a, b) => a - b)
  const parts = []
  let start = sorted[0], prev = sorted[0]
  for (let i = 1; i <= sorted.length; i++) {
    if (i < sorted.length && sorted[i] === prev + 1) { prev = sorted[i]; continue }
    parts.push(start === prev ? `${start}` : `${start}-${prev}`)
    if (i < sorted.length) { start = prev = sorted[i] }
  }
  return parts.join(',')
}

// ---------------------------------------------------------------------------
// Batch tab
// ---------------------------------------------------------------------------
const urlsText = ref('')
const batchParsing = ref(false)
const batchRows = ref([])
const batchSelected = ref([])
const qualityIdx = ref(0)
const concurrency = ref(2)
const batchPumping = ref(false)
const batchDone = ref(0)
const batchTotal = ref(0)

// job_id -> row map + queue for the concurrency pump
let jobRowMap = new Map()
let runningJobs = new Set()
let pendingQueue = []

async function pasteUrls() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) urlsText.value = (urlsText.value ? urlsText.value + '\n' : '') + text.trim()
  } catch {
    ElMessage.warning(t('main_ui.please_enter_url'))
  }
}

async function doBatchParse() {
  const urls = urlsText.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
  if (!urls.length) {
    ElMessage.warning(t('main_ui.please_enter_url'))
    return
  }
  if (urls.length > 50) {
    ElMessage.warning(t('web.batch.too_many', { max: 50 }))
    return
  }
  batchParsing.value = true
  try {
    const data = await analyzeBatch({ urls })
    batchRows.value = (data.results || []).map((r) => ({ ...r, dl_status: '' }))
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    batchParsing.value = false
  }
}

function buildBatchPayload(row) {
  const preset = qualityOptions.value[qualityIdx.value]
  const base = {
    url: row.url,
    path: downloadPath.value,
    is_playlist: row.is_playlist,
    title: row.summary?.title,
    channel: row.summary?.channel,
    thumbnail_url: row.summary?.thumbnail,
    analysis_id: row.analysis_id,
  }
  if (preset.audio) {
    if (row.is_playlist) {
      return { ...base, is_audio_only: true, format_id: null, resolution: '' }
    }
    return { ...base, is_audio_only: true, format_id: 'bestaudio', format_has_audio: false, resolution: '' }
  }
  return { ...base, is_audio_only: false, format_id: preset.format_id, format_has_audio: false, resolution: '' }
}

async function startBatchDownload() {
  if (!batchSelected.value.length) return
  pendingQueue = batchSelected.value.filter((r) => r.ok && !r.dl_status)
  batchTotal.value = pendingQueue.length
  batchDone.value = 0
  jobRowMap = new Map()
  runningJobs = new Set()
  batchPumping.value = true
  pumpBatch()
}

function pumpBatch() {
  while (runningJobs.size < concurrency.value && pendingQueue.length) {
    const row = pendingQueue.shift()
    row.dl_status = 'queued'
    startDownload(buildBatchPayload(row))
      .then(({ job_id }) => {
        jobRowMap.set(job_id, row)
        runningJobs.add(job_id)
        row.dl_status = 'running'
      })
      .catch((e) => {
        row.dl_status = 'error'
        batchDone.value++
        ElMessage.error(`${row.summary?.title || row.url}: ${errText(e)}`)
        checkBatchFinished()
      })
  }
  checkBatchFinished()
}

function checkBatchFinished() {
  if (!batchPumping.value) return
  if (!pendingQueue.length && !runningJobs.size) {
    batchPumping.value = false
    ElNotification({
      title: t('web.batch.done_title'),
      message: t('web.batch.done_message', { count: batchDone.value }),
      type: 'success',
      duration: 6000,
    })
  }
}

// Watch job statuses (avoids onFinished which leaks listeners)
watch(
  () => downloadStore.jobs,
  () => {
    for (const [jobId, row] of [...jobRowMap]) {
      const job = downloadStore.jobs.find((j) => j.job_id === jobId)
      if (!job) continue
      if (['completed', 'error', 'cancelled'].includes(job.status)) {
        row.dl_status = job.status
        jobRowMap.delete(jobId)
        runningJobs.delete(jobId)
        batchDone.value++
        pumpBatch()
      }
    }
  },
  { deep: true }
)

// ---------------------------------------------------------------------------
// Channel tab
// ---------------------------------------------------------------------------
const channelUrl = ref('')
const channelTab = ref('videos')
const channelLimit = ref(100)
const channelParsing = ref(false)
const channelResult = ref(null)
const channelSelected = ref([])
const chQualityIdx = ref(0)
const channelTableRef = ref(null)
const channelJobId = ref(null)

const channelJob = computed(() =>
  downloadStore.jobs.find((j) => j.job_id === channelJobId.value)
)
const chProgressStatus = computed(() => {
  const s = channelJob.value?.status
  if (s === 'completed') return 'success'
  if (s === 'error' || s === 'cancelled') return 'exception'
  return ''
})

async function doChannelParse() {
  if (!channelUrl.value.trim()) {
    ElMessage.warning(t('main_ui.please_enter_url'))
    return
  }
  channelParsing.value = true
  try {
    channelResult.value = await analyzeChannel({
      url: channelUrl.value.trim(),
      tab: channelTab.value,
      limit: channelLimit.value,
    })
    channelSelected.value = []
    if (!channelResult.value.entries.length) {
      ElMessage.warning(t('web.channel.empty'))
    }
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    channelParsing.value = false
  }
}

function selectAllChannel() {
  channelTableRef.value?.toggleAllSelection()
  nextTick(() => {
    if (channelSelected.value.length !== (channelResult.value?.entries.length || 0)) {
      channelTableRef.value?.toggleAllSelection()
    }
  })
}

async function startChannelDownload() {
  const res = channelResult.value
  if (!res || !channelSelected.value.length || !downloadPath.value) return
  const preset = qualityOptions.value[chQualityIdx.value]
  const allSelected = channelSelected.value.length === res.entries.length
  const payload = {
    url: res.channel_info.normalized_url,
    path: downloadPath.value,
    is_playlist: true,
    is_audio_only: !!preset.audio,
    format_id: preset.audio ? null : preset.format_id,
    resolution: '',
    playlist_items: allSelected ? null : condenseIndices(channelSelected.value.map((r) => r.index)),
    title: res.channel_info.title,
    channel: res.channel_info.uploader,
    thumbnail_url: res.entries[0]?.thumbnail || null,
    analysis_id: res.analysis_id,
  }
  try {
    const { job_id } = await startDownload(payload)
    channelJobId.value = job_id
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

async function cancelChannelJob() {
  try { await cancelJob(channelJobId.value) } catch (e) { ElMessage.error(errText(e)) }
}

// ---------------------------------------------------------------------------
onMounted(async () => {
  await settingsStore.fetch()
  if (!downloadPath.value) downloadPath.value = settingsStore.downloadPath
})

watch(() => settingsStore.downloadPath, (v) => { if (v && !downloadPath.value) downloadPath.value = v })
</script>

<style scoped>
.batch-tabs { padding-top: 0; }
.url-row { display: flex; gap: 10px; align-items: center; }
.action-row { margin-top: 12px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.hint { color: var(--yts-text-dim); font-size: 12px; }
.channel-head { display: flex; align-items: baseline; gap: 14px; }
.channel-title { font-weight: 600; font-size: 15px; color: var(--yts-text); }
.cell-video { display: flex; align-items: center; gap: 10px; }
.cell-video img { width: 80px; height: 45px; object-fit: cover; border-radius: 4px; background: #101214; flex: 0 0 80px; }
.thumb-ph { width: 80px; height: 45px; border-radius: 4px; background: #101214; display: flex; align-items: center; justify-content: center; flex: 0 0 80px; opacity: 0.6; }
.cell-meta { min-width: 0; }
.cell-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.cell-sub { color: var(--yts-text-dim); font-size: 12px; }
.progress-line { margin-top: 12px; display: flex; align-items: center; gap: 12px; color: var(--yts-text-dim); font-size: 13px; }
</style>
