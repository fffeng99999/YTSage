<template>
  <div class="dashboard">
    <!-- ===== URL input row ===== -->
    <div class="yts-card">
      <div class="url-row">
        <el-input
          v-model="url"
          :placeholder="settingsStore.genericMode ? t('main_ui.url_placeholder_generic') : t('main_ui.url_placeholder')"
          size="large"
          clearable
          :disabled="analyzing || downloading"
          @keyup.enter="doAnalyze"
          :class="{ 'yts-shake': urlShake }"
        />
        <el-button size="large" @click="pasteUrl" :disabled="analyzing || downloading">
          {{ t('buttons.paste_url') }}
        </el-button>
        <el-button
          size="large"
          type="danger"
          :disabled="!url.trim() || analyzing || downloading"
          :loading="analyzing"
          @click="doAnalyze"
        >
          {{ t('buttons.analyze') }}
        </el-button>
      </div>
      <div v-if="analyzing" class="analyze-progress">
        <el-progress :percentage="analyzePct" :stroke-width="6" striped striped-flow />
        <span class="stage">{{ t(analyzeStageKey) }}</span>
      </div>
    </div>

    <!-- ===== download row ===== -->
    <div class="yts-card">
      <div class="url-row">
        <el-input v-model="downloadPath" size="large" :placeholder="t('settings.download_path')" style="flex:1" :disabled="downloading">
          <template #prepend>{{ t('settings.download_path') }}</template>
        </el-input>
        <el-button size="large" type="danger" :loading="starting" :disabled="!canDownload" @click="startDownload">
          {{ t('buttons.download') }}
        </el-button>
        <el-button v-if="currentJob && currentJob.status === 'running'" size="large" @click="pauseJob">
          {{ t('buttons.pause') }}
        </el-button>
        <el-button v-if="currentJob && currentJob.status === 'paused'" size="large" type="warning" @click="resumeJob">
          {{ t('buttons.resume') }}
        </el-button>
        <el-button v-if="currentJob && ['running', 'paused'].includes(currentJob.status)" size="large" @click="cancelJob">
          {{ t('buttons.cancel') }}
        </el-button>
        <el-button v-if="currentJob && currentJob.status === 'completed' && currentJob.last_file_path" size="large" @click="reveal(currentJob.last_file_path)">
          📁
        </el-button>
      </div>

      <!-- progress -->
      <template v-if="currentJob">
        <el-progress
          :percentage="Math.min(100, currentJob.progress || 0)"
          :stroke-width="14"
          :status="progressStatus"
          style="margin-top: 14px"
        />
        <div class="progress-meta">
          <span>{{ statusText }}</span>
          <span v-if="currentJob.speed">{{ t('download.speed') }}: {{ currentJob.speed }}</span>
          <span v-if="currentJob.eta">{{ t('download.eta') }}: {{ currentJob.eta }}</span>
        </div>
      </template>
    </div>

    <!-- ===== Video info ===== -->
    <div v-if="store.result && !analyzing" class="yts-card">
      <VideoInfoCard />

      <!-- subtitle / sponsorblock / playlist buttons -->
      <div class="action-row">
        <el-button size="small" :class="{ 'yts-active-outline': store.selectedSubtitles.length }" @click="subDialog = true">
          {{ t('main_ui.select_subtitles') }}
        </el-button>
        <span class="count-label">
          {{ store.selectedSubtitles.length
            ? t('main_ui.subtitles_selected', { count: store.selectedSubtitles.length })
            : t('selection.none_selected') }}
        </span>

        <el-button size="small" :class="{ 'yts-active-outline': store.sponsorblockSelected.length }" @click="sbDialog = true">
          {{ t('dialogs.sponsorblock_categories') }}
        </el-button>
        <span class="count-label">
          {{ store.sponsorblockSelected.length
            ? t('selection.count_selected', { count: store.sponsorblockSelected.length })
            : t('selection.none_selected') }}
        </span>

        <template v-if="store.isPlaylist">
          <el-button size="small" @click="plDialog = true">
            {{ t('buttons.select_videos') }}{{ store.playlistAllSelected ? '' : ` (${store.playlistItemsString})` }}
          </el-button>
          <el-button size="small" @click="doExport('txt')">TXT</el-button>
          <el-button size="small" @click="doExport('m3u')">M3U</el-button>
          <el-button size="small" @click="doExport('csv')">CSV</el-button>
          <el-button size="small" @click="doExport('json')">JSON</el-button>
        </template>

        <el-button size="small" :class="{ 'yts-active-outline': store.downloadSection }" @click="trDialog = true">
          {{ t('buttons.trim_video') }}
        </el-button>
      </div>

      <!-- ===== format controls ===== -->
      <div class="action-row">
        <FormatTable />
      </div>

      <div class="action-row">
        <el-checkbox
          v-model="store.mergeSubs"
          :disabled="!store.selectedSubtitles.length || store.mode === 'audio'"
        >{{ t('main_ui.merge_subtitles') }}</el-checkbox>
        <el-checkbox v-model="store.saveThumbnail">{{ t('main_ui.save_thumbnail') }}</el-checkbox>
        <el-checkbox v-model="store.saveDescription">{{ t('main_ui.save_description') }}</el-checkbox>
        <el-popover placement="top" :width="180" trigger="click">
          <template #reference>
            <el-button size="small" text>▸ Embed</el-button>
          </template>
          <EmbedOptionsPanel />
        </el-popover>
      </div>
    </div>

    <!-- ===== recent downloads ===== -->
    <div class="yts-card" v-if="recentJobs.length">
      <div class="yts-card-title">{{ t('history.title') }}</div>
      <div v-for="j in recentJobs" :key="j.job_id" class="recent-row">
        <span class="recent-name">{{ j.current_filename || j.title || j.job_id }}</span>
        <el-progress :percentage="Math.min(100, j.progress || 0)" style="width: 200px" :stroke-width="8" />
        <el-tag size="small" :type="statusTag(j.status)">{{ j.status }}</el-tag>
      </div>
    </div>

    <!-- dialogs -->
    <SubtitleDialog v-model="subDialog" />
    <SponsorBlockDialog v-model="sbDialog" />
    <PlaylistDialog v-model="plDialog" />
    <TimeRangeDialog v-model="trDialog" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElNotification } from 'element-plus'
import { useRoute } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useDownloadStore } from '@/stores/download'
import { useSettingsStore } from '@/stores/settings'
import { startDownload as apiStartDownload, pauseJob as apiPause, resumeJob as apiResume, cancelJob as apiCancel } from '@/api/download'
import { exportPlaylist } from '@/api/tools'
import { errText } from '@/api/http'
import { useReveal } from '@/composables/useReveal'
import { playNotification } from '@/composables/useSound'
import VideoInfoCard from '@/components/VideoInfoCard.vue'
import FormatTable from '@/components/FormatTable.vue'
import SubtitleDialog from '@/components/SubtitleDialog.vue'
import SponsorBlockDialog from '@/components/SponsorBlockDialog.vue'
import PlaylistDialog from '@/components/PlaylistDialog.vue'
import TimeRangeDialog from '@/components/TimeRangeDialog.vue'

const { t } = useI18n()
const route = useRoute()
const store = useAnalysisStore()
const downloadStore = useDownloadStore()
const settingsStore = useSettingsStore()
const { reveal } = useReveal()

const url = ref('')
const downloadPath = ref('')
const analyzing = ref(false)
const analyzePct = ref(0)
const analyzeStageKey = ref('main_ui.analyzing_preparing')
const urlShake = ref(false)
const starting = ref(false)
const currentJobId = ref(null)

const subDialog = ref(false)
const sbDialog = ref(false)
const plDialog = ref(false)
const trDialog = ref(false)

const currentJob = computed(() =>
  downloadStore.jobs.find((j) => j.job_id === currentJobId.value)
)
const downloading = computed(() =>
  currentJob.value && ['running', 'paused', 'pending'].includes(currentJob.value.status)
)
const canDownload = computed(() =>
  !!url.value.trim() && !!downloadPath.value && !analyzing.value && !downloading.value
)
const recentJobs = computed(() => downloadStore.jobs.slice(-5).reverse())

const progressStatus = computed(() => {
  const s = currentJob.value?.status
  if (s === 'completed') return 'success'
  if (s === 'error' || s === 'cancelled') return 'exception'
  return ''
})

const statusText = computed(() => {
  const j = currentJob.value
  if (!j) return ''
  switch (j.status) {
    case 'paused': return t('download.paused')
    case 'cancelled': return t('download.cancelled')
    case 'completed':
      if (j.file_exists) return t('status.file_exists')
      return j.is_audio_only ? t('download.audio_completed') : t('download.video_completed')
    case 'error':
      return j.error_key ? t(j.error_key, { error: j.error }) : (j.error || t('download.completed'))
    case 'running':
      if (j.stage === 'merging') return t('download.merging_formats')
      if (j.stage === 'sponsorblock') return t('download.removing_sponsor_segments')
      if (j.stage === 'subtitles') return t('download.downloading_subtitle')
      return t('download.downloading')
    default: return t('download.preparing')
  }
})

function statusTag(s) {
  return { completed: 'success', error: 'danger', cancelled: 'info', paused: 'warning', running: 'primary' }[s] || 'info'
}

async function pasteUrl() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) url.value = text.trim()
  } catch {
    ElMessage.warning(t('main_ui.please_enter_url'))
  }
}

async function doAnalyze() {
  if (!url.value.trim()) {
    urlShake.value = true
    setTimeout(() => (urlShake.value = false), 400)
    ElMessage.warning(t('main_ui.please_enter_url'))
    return
  }
  analyzing.value = true
  analyzePct.value = 5
  // Fake staged progress like the official AnalysisThread
  const stages = [
    ['main_ui.analyzing_extracting_basic', 15],
    ['main_ui.analyzing_extracting_ytdlp', 30],
    ['main_ui.analyzing_processing_data', 60],
    ['main_ui.analyzing_fetching_first_video', 70],
    ['main_ui.analyzing_processing_formats', 85],
  ]
  let si = 0
  const timer = setInterval(() => {
    if (si < stages.length) {
      analyzeStageKey.value = stages[si][0]
      analyzePct.value = stages[si][1]
      si++
    } else if (analyzePct.value < 95) {
      analyzePct.value += 3
    }
  }, 900)
  try {
    await store.analyze(url.value.trim())
    analyzePct.value = 100
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    clearInterval(timer)
    setTimeout(() => { analyzing.value = false }, 300)
  }
}

async function doExport(fmt) {
  try {
    await exportPlaylist(store.result?.analysis_id, fmt, store.result?.playlist_info?.title)
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

async function startDownload() {
  const selection = store.buildDownloadSelection()
  if (!selection) {
    ElMessage.warning(t('download.please_select_format'))
    return
  }
  starting.value = true
  try {
    const s = settingsStore.settings || {}
    const payload = {
      url: url.value.trim(),
      path: downloadPath.value,
      ...selection,
      subtitle_langs: store.selectedSubtitles,
      merge_subs: store.mergeSubs,
      enable_sponsorblock: store.sponsorblockSelected.length > 0,
      sponsorblock_categories: store.sponsorblockSelected,
      save_description: store.saveDescription,
      save_thumbnail: store.saveThumbnail,
      embed_chapters: store.embedChapters,
      embed_metadata: store.embedMetadata,
      embed_thumbnail: store.embedThumbnail,
      download_section: store.downloadSection,
      force_keyframes: store.forceKeyframes,
      title: store.isPlaylist ? store.result?.playlist_info?.title : store.videoSummary.title,
      channel: store.videoSummary.channel,
      duration: store.videoSummary.duration_string,
      thumbnail_url: store.result?.thumbnail_url,
      analysis_id: store.result?.analysis_id,
    }
    const { job_id } = await apiStartDownload(payload)
    currentJobId.value = job_id
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    starting.value = false
  }
}

async function pauseJob() { try { await apiPause(currentJobId.value) } catch (e) { ElMessage.error(errText(e)) } }
async function resumeJob() { try { await apiResume(currentJobId.value) } catch (e) { ElMessage.error(errText(e)) } }
async function cancelJob() { try { await apiCancel(currentJobId.value) } catch (e) { ElMessage.error(errText(e)) } }

// completion notification + sound (official play_notification_sound)
downloadStore.onFinished((job, success) => {
  if (job.job_id !== currentJobId.value) return
  if (success) {
    playNotification()
    ElNotification({
      title: t('download.completed'),
      message: job.current_filename || job.title || job.job_id,
      type: 'success',
      duration: 5000,
    })
  } else if (job.status === 'error') {
    ElNotification({
      title: t('main_ui.error_title'),
      message: job.error_key ? t(job.error_key, { error: job.error }) : job.error,
      type: 'error',
      duration: 8000,
    })
  }
})

onMounted(async () => {
  await settingsStore.fetch()
  downloadPath.value = settingsStore.downloadPath
  // Redownload from history: ?url=...&opts=...
  if (route.query.url) {
    url.value = String(route.query.url)
    if (route.query.opts) {
      try { store.loadSelectionFromOptions(JSON.parse(String(route.query.opts))) } catch {}
    }
    doAnalyze()
  }
})

watch(() => settingsStore.downloadPath, (v) => { if (v && !downloadPath.value) downloadPath.value = v })
</script>

<style scoped>
.url-row { display: flex; gap: 10px; align-items: center; }
.analyze-progress { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.analyze-progress .el-progress { flex: 1; }
.stage { color: var(--yts-text-dim); font-size: 13px; white-space: nowrap; }
.action-row { margin-top: 12px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.count-label { color: var(--yts-text-dim); font-size: 12px; }
.progress-meta {
  display: flex; gap: 20px; justify-content: center;
  margin-top: 8px; color: var(--yts-text-dim); font-size: 13px;
}
.recent-row {
  display: flex; align-items: center; gap: 12px; padding: 6px 0;
  border-bottom: 1px solid var(--yts-border);
}
.recent-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
</style>
