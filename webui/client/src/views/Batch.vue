<template>
  <div class="batch-page">
    <!-- ===== shared download defaults (driven by global settings) ===== -->
    <div class="yts-card">
      <div class="action-row" style="margin-top: 0">
        <span class="lbl">{{ t('settings.download_path') }}</span>
        <el-input v-model="downloadPath" style="flex: 1; min-width: 240px" :placeholder="t('settings.download_path')" />
        <span class="lbl">{{ t('web.batch.quality') }}</span>
        <el-select v-model="qualityIdx" style="width: 190px">
          <el-option v-for="(q, i) in qualityOptions" :key="q.key" :label="q.label" :value="i" />
        </el-select>
        <span class="lbl">{{ t('web.batch.concurrency') }}</span>
        <el-select v-model="concurrency" style="width: 90px">
          <el-option v-for="n in [1, 2, 3, 5]" :key="n" :label="n" :value="n" />
        </el-select>
      </div>
      <div class="action-row">
        <el-checkbox v-model="optMergeSubs">{{ t('main_ui.merge_subtitles') }}</el-checkbox>
        <el-checkbox v-model="optSaveThumbnail">{{ t('main_ui.save_thumbnail') }}</el-checkbox>
        <el-checkbox v-model="optSaveDescription">{{ t('main_ui.save_description') }}</el-checkbox>
        <el-tooltip :content="t('web.batch.sponsorblock_tip')" placement="top">
          <el-checkbox v-model="optSponsorblock">{{ t('dialogs.sponsorblock_categories') }}</el-checkbox>
        </el-tooltip>
      </div>
      <div class="hint" style="margin-top: 6px">{{ t('web.batch.defaults_hint') }}</div>
      <div class="hint">{{ t('web.batch.options_hint') }}</div>
    </div>

    <el-tabs v-model="activeTab" class="yts-card batch-tabs">
      <!-- ================= Batch download ================= -->
      <el-tab-pane :label="t('web.batch.tab')" name="batch">
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

        <template v-if="batchRows.length">
          <div class="action-row">
            <el-button
              type="danger"
              :disabled="!batchSelected.length || !downloadPath || batchPumping"
              :loading="batchPumping"
              @click="startBatchDownload"
            >
              {{ t('web.batch.download_selected', { count: batchSelected.length }) }}
            </el-button>
            <el-button v-if="batchDone > 0" text @click="router.push('/jobs')">{{ t('web.batch.go_to_jobs') }}</el-button>
            <span v-if="batchPumping" class="hint">{{ t('web.batch.progress', { done: batchDone, total: batchTotal }) }}</span>
          </div>

          <el-table
            :data="batchRows"
            max-height="480"
            row-key="url"
            @selection-change="(rows) => (batchSelected = rows)"
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
            <el-table-column :label="t('web.batch.col_codec')" width="130">
              <template #default="{ row }">
                <span v-if="row.ok && !row.is_playlist" class="hint">{{ codecLabel(row.picked) }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('web.batch.col_status')" width="180">
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
        </template>
      </el-tab-pane>

      <!-- ================= Channel download ================= -->
      <el-tab-pane :label="t('web.channel.tab')" name="channel">
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
          <span class="lbl">{{ t('web.channel.page_size') }}</span>
          <el-select v-model="chPageSize" style="width: 110px" @change="onPageSizeChange">
            <el-option v-for="n in [20, 50, 100, 200]" :key="n" :label="n" :value="n" />
          </el-select>
        </div>

        <template v-if="channelResult">
          <div class="channel-head">
            <span class="channel-title">{{ channelResult.channel_info.title || '-' }}</span>
            <span class="hint">
              {{ channelResult.total ? t('web.channel.total', { count: channelResult.total }) : t('web.channel.loaded', { count: loadedCount }) }}
            </span>
            <span class="hint">{{ t('web.channel.selected', { count: channelSelected.length }) }}</span>
          </div>

          <div class="action-row">
            <el-input
              v-model="chSearch"
              :placeholder="t('web.channel.search_placeholder')"
              clearable
              style="width: 260px"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button
              type="danger"
              :disabled="!channelSelected.length || !downloadPath || channelPumping"
              :loading="channelPumping"
              @click="startChannelDownload"
            >
              {{ t('web.batch.download_selected', { count: channelSelected.length }) }}
            </el-button>
            <el-button v-if="channelDone > 0" text @click="router.push('/jobs')">{{ t('web.batch.go_to_jobs') }}</el-button>
            <span v-if="channelPumping" class="hint">{{ t('web.batch.progress', { done: channelDone, total: channelTotal }) }}</span>
          </div>

          <el-table
            ref="channelTableRef"
            :data="displayEntries"
            max-height="480"
            row-key="index"
            @selection-change="onChannelSelChange"
          >
            <el-table-column type="selection" width="42" reserve-selection />
            <el-table-column :label="t('web.channel.col_pos')" width="80">
              <template #default="{ row }">{{ row.index }}</template>
            </el-table-column>
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
                    <div class="cell-sub">
                      <el-tag v-if="isChannelSelected(row.index)" size="small" type="success">{{ t('web.channel.selected_tag') }}</el-tag>
                      <span v-if="searching && isChannelSelected(row.index) && !matches(row)">{{ t('web.channel.pinned_note') }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('video_info.duration')" width="100">
              <template #default="{ row }">{{ fmtDur(row.duration) }}</template>
            </el-table-column>
            <el-table-column :label="t('web.batch.col_status')" width="150">
              <template #default="{ row }">
                <el-tag v-if="row.dl_status === 'queued'" size="small" type="info">{{ t('web.batch.queued') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'running'" size="small">{{ t('download.downloading') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'completed'" size="small" type="success">{{ t('download.completed') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'error'" size="small" type="danger">{{ t('web.batch.failed') }}</el-tag>
                <el-tag v-else-if="row.dl_status === 'cancelled'" size="small" type="info">{{ t('download.cancelled') }}</el-tag>
              </template>
            </el-table-column>
          </el-table>

          <div class="pager-row">
            <el-pagination
              v-model:current-page="chPage"
              :page-size="chPageSize"
              :total="paginationTotal"
              :pager-count="7"
              layout="prev, pager, next, jumper"
              background
              :disabled="channelParsing"
              @current-change="loadChannelPage"
            />
            <el-button
              v-if="!channelResult.total && channelResult.has_more"
              text
              size="small"
              :disabled="channelParsing"
              @click="loadChannelPage(chPage + 1)"
            >
              {{ t('web.channel.next_page') }}
            </el-button>
          </div>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { analyzeBatch, analyzeChannel } from '@/api/batch'
import { startDownload } from '@/api/download'
import { errText } from '@/api/http'
import { SPONSORBLOCK_CATEGORIES } from '@/stores/analysis'
import { readClipboardText } from '@/composables/useClipboard'
import { useSessionRef } from '@/composables/useSessionRef'
import { useDownloadStore } from '@/stores/download'
import { useSettingsStore } from '@/stores/settings'

const { t, te } = useI18n()
const router = useRouter()
const downloadStore = useDownloadStore()
const settingsStore = useSettingsStore()

const activeTab = ref('batch')
const downloadPath = ref('')
const concurrency = ref(2)

// Download options shared by both tabs (same semantics as the Dashboard):
// when a video has no subtitles/thumbnail/description, yt-dlp just skips it.
const optMergeSubs = ref(false)
const optSaveThumbnail = ref(false)
const optSaveDescription = ref(false)
// SponsorBlock stays OFF by default: its ModifyChapters post-processor can hit
// an upstream ffmpeg failure on subtitle files ("Result too large", yt-dlp
// #9929), so it must be an explicit opt-in.
const optSponsorblock = ref(false)

/* --------------------------------------------------------------------------
 * Quality selection with codec priority (configurable in Settings -> Format,
 * default av01 > vp09 > avc1)
 * ------------------------------------------------------------------------ */
const CODEC_LABELS = { av01: 'AV1', vp09: 'VP9', avc1: 'AVC/H.264' }
const ALL_CODEC_KEYS = ['av01', 'vp09', 'avc1']

// Full preference order: user-prioritized codecs first (Settings drag UI),
// then any codec the user left in the pool as last-resort fallback, so a
// download never fails just because its only codec was deprioritized.
const codecOrder = computed(() => {
  const pref = (settingsStore.settings && settingsStore.settings.codec_priority) || ALL_CODEC_KEYS
  const valid = pref.filter((k) => ALL_CODEC_KEYS.includes(k))
  return [...valid, ...ALL_CODEC_KEYS.filter((k) => !valid.includes(k))]
})

const qualityOptions = computed(() => {
  const s = settingsStore.settings || {}
  const dq = s.default_video_quality
  const opts = [{ key: 'auto', height: dq ? Number(dq) : null, label: t('web.batch.q_auto') }]
  for (const h of [2160, 1440, 1080, 720, 480, 360, 240]) {
    opts.push({ key: `h${h}`, height: h, label: `${h}p` })
  }
  opts.push({ key: 'audio', height: null, audio: true, label: t('web.batch.audio_only') })
  return opts
})
const qualityIdx = ref(0)
const currentQuality = computed(() => qualityOptions.value[qualityIdx.value] || qualityOptions.value[0])

function codecFamily(vcodec) {
  const s = (vcodec || '').toLowerCase()
  if (s.startsWith('av01')) return 'av01'
  if (s.startsWith('vp09') || s.startsWith('vp9')) return 'vp09'
  if (s.startsWith('avc')) return 'avc1'
  return null
}
function codecRank(vcodec) {
  const fam = codecFamily(vcodec)
  if (!fam) return 99
  return codecOrder.value.indexOf(fam)
}
function codecName(vcodec) {
  const fam = codecFamily(vcodec)
  return (fam && CODEC_LABELS[fam]) || (vcodec || '-')
}

/**
 * Pick video+audio formats exactly like the Dashboard single-video flow,
 * but ordering codecs av01 > vp09 > avc1 and only falling back to the next
 * codec when the preferred one is unavailable.
 */
function pickFormats(formats, height, audioOnly) {
  const list = formats || []
  const isAudio = (f) => (!f.vcodec || f.vcodec === 'none') && f.acodec && f.acodec !== 'none'
  const isVideo = (f) => f.vcodec && f.vcodec !== 'none'
  const audios = list.filter(isAudio).sort((a, b) => (b.abr || b.tbr || 0) - (a.abr || a.tbr || 0))

  if (audioOnly) {
    return { audioOnly: true, v: audios[0] || null, a: null, fallback: 'bestaudio' }
  }
  let videos = list.filter(isVideo)
  if (height) videos = videos.filter((f) => (f.height || 0) <= height)
  if (!videos.length) return null
  videos.sort((x, y) => codecRank(x.vcodec) - codecRank(y.vcodec)
    || (y.height || 0) - (x.height || 0)
    || (y.tbr || 0) - (x.tbr || 0))
  const v = videos[0]
  const hasAudio = !!(v.acodec && v.acodec !== 'none')
  return { audioOnly: false, v, a: hasAudio ? null : (audios[0] || null), fallback: null }
}

/** Codec-priority selector chain for videos whose format list we don't have. */
function chainSelector(height, audioOnly) {
  if (audioOnly) return 'bestaudio/best'
  const h = height ? `[height<=${height}]` : ''
  // codecOrder.value keys are exactly the yt-dlp vcodec prefixes (av01/vp09/avc1)
  const parts = codecOrder.value.map(
    (c) => `bv*[vcodec^=${c}]${h}+ba/b*[vcodec^=${c}]${h}`
  )
  parts.push('bv*+ba/b')
  return parts.join('/')
}

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
function codecLabel(pick) {
  if (!pick || !pick.v) return ''
  return `${codecName(pick.v.vcodec)} · ${pick.v.height || '?'}p`
}

/* --------------------------------------------------------------------------
 * Shared concurrency pump (used by both tabs)
 * ------------------------------------------------------------------------ */
function createPump(onAllDone) {
  const state = reactive({ pumping: false, done: 0, total: 0 })
  let jobRowMap = new Map()
  let running = new Set()
  let queue = []

  function pump() {
    while (running.size < concurrency.value && queue.length) {
      const row = queue.shift()
      row.dl_status = 'queued'
      startDownload(row.payload)
        .then(({ job_id }) => {
          jobRowMap.set(job_id, row)
          running.add(job_id)
          row.dl_status = 'running'
        })
        .catch((e) => {
          row.dl_status = 'error'
          state.done++
          ElMessage.error(`${row.title || row.payload.url}: ${errText(e)}`)
          checkDone()
        })
    }
    checkDone()
  }

  function checkDone() {
    if (!state.pumping) return
    if (!queue.length && !running.size) {
      state.pumping = false
      onAllDone(state.done)
    }
  }

  function start(rows) {
    queue = rows.slice()
    state.total = queue.length
    state.done = 0
    jobRowMap = new Map()
    running = new Set()
    state.pumping = true
    pump()
  }

  function onJobsChanged(jobs) {
    for (const [jobId, row] of [...jobRowMap]) {
      const job = jobs.find((j) => j.job_id === jobId)
      if (!job) continue
      if (['completed', 'error', 'cancelled'].includes(job.status)) {
        row.dl_status = job.status
        jobRowMap.delete(jobId)
        running.delete(jobId)
        state.done++
        pump()
      }
    }
  }

  return { state, start, onJobsChanged }
}

function doneNotification(count) {
  ElNotification({
    title: t('web.batch.done_title'),
    message: t('web.batch.done_message', { count }),
    type: 'success',
    duration: 6000,
  })
}

/* --------------------------------------------------------------------------
 * Batch tab
 * ------------------------------------------------------------------------ */
const urlsText = useSessionRef('ytsage_session_batch_urls', '')
const batchParsing = ref(false)
const batchRows = ref([])
const batchSelected = ref([])

const batchPump = createPump(doneNotification)
const batchPumping = computed(() => batchPump.state.pumping)
const batchDone = computed(() => batchPump.state.done)
const batchTotal = computed(() => batchPump.state.total)

async function pasteUrls() {
  const text = await readClipboardText()
  if (text) {
    urlsText.value = (urlsText.value ? urlsText.value + '\n' : '') + text
  } else {
    ElMessage.warning(t('main_ui.please_enter_url'))
  }
}

async function doBatchParse() {
  const urls = urlsText.value.split('\n').map((s) => s.trim()).filter(Boolean)
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
    batchRows.value = (data.results || []).map((r) => ({ ...r, dl_status: '', picked: null }))
    applyQualityToBatchRows()
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    batchParsing.value = false
  }
}

// Re-resolve format picks whenever the quality choice changes
function applyQualityToBatchRows() {
  const q = currentQuality.value
  for (const row of batchRows.value) {
    if (!row.ok || row.is_playlist || row.dl_status) continue
    row.picked = pickFormats(row.formats, q.height, q.audio)
  }
}
watch(currentQuality, applyQualityToBatchRows)
watch(codecOrder, applyQualityToBatchRows)

/** Build a payload that mirrors Dashboard's single-video download exactly. */
function buildBatchPayload(row) {
  const q = currentQuality.value
  const base = {
    url: row.url,
    path: downloadPath.value,
    is_playlist: row.is_playlist,
    title: row.summary?.title,
    channel: row.summary?.channel,
    duration: row.summary?.duration_string,
    thumbnail_url: row.summary?.thumbnail,
    analysis_id: row.analysis_id,
    subtitle_langs: defaultSubtitleLangs(row.subtitles),
    merge_subs: optMergeSubs.value,
    save_thumbnail: optSaveThumbnail.value,
    save_description: optSaveDescription.value,
    // Opt-in only (see optSponsorblock note)
    enable_sponsorblock: optSponsorblock.value,
    sponsorblock_categories: optSponsorblock.value
      ? SPONSORBLOCK_CATEGORIES.filter((c) => c.default).map((c) => c.id)
      : [],
  }
  if (row.is_playlist) {
    // whole playlist: reuse the existing playlist download path
    return {
      ...base,
      is_audio_only: !!q.audio,
      format_id: chainSelector(q.height, q.audio),
      format_has_audio: true,
      resolution: '',
    }
  }
  const pick = row.picked || pickFormats(row.formats, q.height, q.audio)
  if (!pick || !pick.v) {
    // no usable format under the cap -> chain selector handles it server-side
    return {
      ...base,
      is_audio_only: !!q.audio,
      format_id: chainSelector(q.height, q.audio),
      format_has_audio: true,
      resolution: '',
    }
  }
  if (q.audio) {
    return {
      ...base,
      is_audio_only: true,
      format_id: pick.v.format_id,
      format_has_audio: false,
      audio_format_ids: [],
      resolution: '',
    }
  }
  return {
    ...base,
    is_audio_only: false,
    format_id: pick.v.format_id,
    format_has_audio: !!(pick.v.acodec && pick.v.acodec !== 'none'),
    audio_format_ids: pick.a ? [pick.a.format_id] : [],
    resolution: '',
  }
}

/** Global default subtitle language -> subtitle selection (Dashboard parity). */
function defaultSubtitleLangs(subtitles) {
  const s = settingsStore.settings || {}
  const dsl = s.default_subtitle_language
  if (!dsl || !subtitles || !subtitles.length) return null
  const langs = String(dsl).split(',').map((x) => x.trim()).filter(Boolean)
  if (!langs.length) return null
  return subtitles
    .filter((x) => langs.includes(x.code))
    .map((x) => (x.type === 'auto' ? `${x.code} - Auto-generated` : x.code))
}

/** Global default subtitle language as bare codes (for channel rows, where
 * flat parsing gives no per-video subtitle list; yt-dlp skips missing ones). */
function defaultSubtitleCodes() {
  const s = settingsStore.settings || {}
  const dsl = s.default_subtitle_language
  if (!dsl) return null
  const langs = String(dsl).split(',').map((x) => x.trim()).filter(Boolean)
  return langs.length ? langs : null
}

async function startBatchDownload() {
  const q = currentQuality.value
  const rows = batchSelected.value.filter((r) => r.ok && !r.dl_status)
  if (!rows.length) return
  if (!downloadPath.value) {
    ElMessage.warning(t('web.batch.need_path'))
    return
  }
  for (const row of rows) {
    if (!row.picked && !row.is_playlist) row.picked = pickFormats(row.formats, q.height, q.audio)
    row.payload = buildBatchPayload(row)
    row.title = row.summary?.title
  }
  batchPump.start(rows)
}

/* --------------------------------------------------------------------------
 * Channel tab (paginated + fuzzy search, selection pinned to top)
 * ------------------------------------------------------------------------ */
const channelUrl = useSessionRef('ytsage_session_channel_url', '')
const channelTab = ref('videos')
const channelParsing = ref(false)
const channelResult = ref(null)
const chPage = ref(1)
const chPageSize = ref(50)
const chSearch = ref('')
const channelTableRef = ref(null)
const pageEntries = ref([])
// global index -> entry, accumulated across pages (keeps selection rows alive)
const loadedEntries = reactive(new Map())

const channelPump = createPump(doneNotification)
const channelPumping = computed(() => channelPump.state.pumping)
const channelDone = computed(() => channelPump.state.done)
const channelTotal = computed(() => channelPump.state.total)

const channelSelected = ref([])
const searching = computed(() => !!chSearch.value.trim())
const loadedCount = computed(() => loadedEntries.size)

// displayEntries re-sorts (pins selected to top) based on selection, so guard
// against a selection-change feedback loop (order-insensitive set compare).
function onChannelSelChange(rows) {
  const prev = channelSelected.value
  if (prev.length === rows.length) {
    const set = new Set(rows.map((r) => r.index))
    if (prev.every((r) => set.has(r.index))) return
  }
  channelSelected.value = rows
}

const selectedIndexes = computed(() => new Set(channelSelected.value.map((r) => r.index)))
function isChannelSelected(idx) {
  return selectedIndexes.value.has(idx)
}

function matches(entry) {
  const kw = chSearch.value.trim().toLowerCase()
  if (!kw) return true
  return (entry.title || '').toLowerCase().includes(kw) || (entry.id || '').toLowerCase().includes(kw)
}

const displayEntries = computed(() => {
  if (!searching.value) return pageEntries.value
  // Selected videos stay visible and are pinned at the top; the rest of the
  // page is filtered by the keyword. Selected rows are never hidden.
  const selected = [...loadedEntries.values()]
    .filter((e) => isChannelSelected(e.index))
    .sort((a, b) => a.index - b.index)
  const selSet = new Set(selected.map((e) => e.index))
  const rest = pageEntries.value.filter((e) => !selSet.has(e.index) && matches(e))
  return [...selected, ...rest]
})

const paginationTotal = computed(() => {
  const r = channelResult.value
  if (!r) return 0
  if (r.total) return r.total
  // unknown total: allow one page past what we've loaded
  return (r.page || chPage.value) * (r.page_size || chPageSize.value) + (r.has_more ? (r.page_size || chPageSize.value) : 0)
})

function mergeEntries(entries) {
  // Keep ONE canonical object per global index (shared between the table,
  // loadedEntries and the download pump) so in-place dl_status updates show.
  const merged = []
  for (const e of entries) {
    let row = loadedEntries.get(e.index)
    if (row) Object.assign(row, e)
    else { row = e; loadedEntries.set(e.index, e) }
    merged.push(row)
  }
  return merged
}

async function loadChannelPage(page) {
  const r = channelResult.value
  if (!r) return
  channelParsing.value = true
  try {
    const data = await analyzeChannel({
      url: r.channel_info.normalized_url,
      tab: r.channel_info.tab,
      page,
      page_size: chPageSize.value,
    })
    channelResult.value = data
    chPage.value = data.page
    pageEntries.value = mergeEntries((data.entries || []).map((e) => ({ ...e, dl_status: '' })))
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    channelParsing.value = false
  }
}

function onPageSizeChange() {
  if (channelResult.value) loadChannelPage(1)
}

async function doChannelParse() {
  if (!channelUrl.value.trim()) {
    ElMessage.warning(t('main_ui.please_enter_url'))
    return
  }
  channelParsing.value = true
  loadedEntries.clear()
  pageEntries.value = []
  chSearch.value = ''
  channelSelected.value = []
  channelTableRef.value?.clearSelection()
  try {
    const data = await analyzeChannel({
      url: channelUrl.value.trim(),
      tab: channelTab.value,
      page: 1,
      page_size: chPageSize.value,
    })
    channelResult.value = data
    chPage.value = data.page
    pageEntries.value = mergeEntries((data.entries || []).map((e) => ({ ...e, dl_status: '' })))
    if (!pageEntries.value.length) ElMessage.warning(t('web.channel.empty'))
  } catch (e) {
    channelResult.value = null
    ElMessage.error(errText(e))
  } finally {
    channelParsing.value = false
  }
}

/**
 * Each selected channel video becomes its own single-video download job
 * (same download path as the Dashboard), using the codec-priority chain
 * selector because flat parsing has no per-video format list.
 */
async function startChannelDownload() {
  if (!channelSelected.value.length) return
  if (!downloadPath.value) {
    ElMessage.warning(t('web.batch.need_path'))
    return
  }
  const q = currentQuality.value
  const rows = channelSelected.value
    .map((r) => loadedEntries.get(r.index) || r)
    .filter((r) => !r.dl_status)
  if (!rows.length) return
  for (const row of rows) {
    row.payload = {
      url: row.url,
      path: downloadPath.value,
      is_playlist: false,
      is_audio_only: !!q.audio,
      format_id: chainSelector(q.height, q.audio),
      format_has_audio: true,
      resolution: '',
      title: row.title,
      channel: channelResult.value.channel_info.uploader,
      duration: fmtDur(row.duration),
      thumbnail_url: row.thumbnail,
      // Global default subtitle language (codes only - flat parsing has no
      // per-video subtitle list; yt-dlp skips languages a video lacks)
      subtitle_langs: defaultSubtitleCodes(),
      merge_subs: optMergeSubs.value,
      save_thumbnail: optSaveThumbnail.value,
      save_description: optSaveDescription.value,
      enable_sponsorblock: optSponsorblock.value,
      sponsorblock_categories: optSponsorblock.value
        ? SPONSORBLOCK_CATEGORIES.filter((c) => c.default).map((c) => c.id)
        : [],
    }
  }
  channelPump.start(rows)
}

/* --------------------------------------------------------------------------
 * job status watcher (avoids onFinished which leaks listeners)
 * ------------------------------------------------------------------------ */
watch(
  () => downloadStore.jobs,
  () => {
    batchPump.onJobsChanged(downloadStore.jobs)
    channelPump.onJobsChanged(downloadStore.jobs)
  },
  { deep: true }
)

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
.lbl { color: var(--yts-text-dim); font-size: 13px; white-space: nowrap; }
.channel-head { display: flex; align-items: baseline; gap: 14px; margin-top: 12px; flex-wrap: wrap; }
.channel-title { font-weight: 600; font-size: 15px; color: var(--yts-text); }
.cell-video { display: flex; align-items: center; gap: 10px; }
.cell-video img { width: 80px; height: 45px; object-fit: cover; border-radius: 4px; background: #101214; flex: 0 0 80px; }
.thumb-ph { width: 80px; height: 45px; border-radius: 4px; background: #101214; display: flex; align-items: center; justify-content: center; flex: 0 0 80px; opacity: 0.6; }
.cell-meta { min-width: 0; }
.cell-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.cell-sub { color: var(--yts-text-dim); font-size: 12px; display: flex; gap: 6px; align-items: center; }
.pager-row { margin-top: 12px; display: flex; align-items: center; gap: 12px; justify-content: center; }
</style>
