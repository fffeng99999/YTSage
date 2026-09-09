<template>
  <div class="dash-page">
    <!-- Overview: stats card (left) + trend chart (right), dysync layout 4:6 -->
    <div class="dash-top">
      <div class="yts-card stats-left">
        <div class="stat-header">
          <div class="main-stat">
            <span class="stat-meta">{{ t('web.sync.stat_total_videos') }}</span>
            <div class="stat-value">{{ st.total_videos ?? 0 }}</div>
          </div>
          <div class="main-stat">
            <span class="stat-meta">{{ t('web.sync.stat_storage') }}</span>
            <div class="stat-value">{{ fmtGB(st.total_size) }} <span class="unit">GB</span></div>
          </div>
        </div>
        <div class="stat-subitems">
          <div v-for="k in KINDS" :key="k.key" class="subitem">
            <div class="subitem-icon" :class="k.cls"><el-icon><component :is="k.icon" /></el-icon></div>
            <span class="subitem-meta">{{ t(k.labelKey) }}</span>
            <span class="subitem-value">
              {{ st[k.countKey] ?? 0 }}<span class="split" v-if="(st[k.countKey] || 0) > 0">/{{ fmtGB(st[k.sizeKey]) }}G</span>
            </span>
          </div>
        </div>
      </div>

      <div class="yts-card chart-right">
        <div class="chart-head">
          <span class="chart-title">{{ t('web.sync.trend_7days') }}</span>
          <el-button text size="small" @click="openFullChart" :title="t('web.sync.fullscreen')">
            <el-icon><FullScreen /></el-icon>
          </el-button>
        </div>
        <div class="chart-box" ref="chartBoxRef">
          <svg v-if="trend.length" :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none" class="trend-svg">
            <line v-for="g in gridYs" :key="g" :x1="padL" :x2="CW - padR" :y1="g" :y2="g" class="grid-line" />
            <template v-for="(s, si) in series" :key="s.key">
              <polyline :points="stackPoints(si)" class="trend-line" :style="{ stroke: s.color }" />
            </template>
            <text v-for="(d, i) in trend" :key="d.date" :x="xPos(i)" :y="CH - 4" class="axis-label" text-anchor="middle">
              {{ d.date.slice(5) }}
            </text>
          </svg>
          <el-empty v-else :description="t('web.sync.no_trend')" :image-size="50" />
        </div>
        <div class="legend">
          <span v-for="s in series" :key="s.key" class="legend-item">
            <i :style="{ background: s.color }"></i>{{ t(s.labelKey) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Author ranking (dysync: 视频作者 grid, infinite scroll, dblclick delete) -->
    <div class="yts-card authors-card">
      <div class="authors-head">
        <el-badge :value="authorTotal" :max="9999" type="primary">
          <h3 class="section-title">{{ t('web.sync.author_stats') }}</h3>
        </el-badge>
        <span class="hint">{{ t('web.sync.author_dblclick_hint') }}</span>
      </div>
      <div class="authors-grid">
        <div v-for="a in authors" :key="a.channel" class="author-card" @dblclick="deleteAuthor(a)">
          <div class="author-row">
            <div class="author-avatar">{{ (a.channel || '?').charAt(0).toUpperCase() }}</div>
            <div class="author-info">
              <div class="author-name" :title="a.channel">{{ a.channel }}</div>
              <div class="author-stats">{{ t('web.sync.author_synced') }}: {{ a.video_count }} · {{ fmtGB(a.total_size) }}G</div>
            </div>
          </div>
          <div class="author-progress">
            <div class="progress-bar" :style="{ width: pct(a.video_count) + '%' }"></div>
          </div>
        </div>
      </div>
      <div ref="loadMoreRef" class="load-more">
        <el-icon v-if="authorLoading" class="is-loading"><Loading /></el-icon>
        <span v-else-if="authorHasMore">{{ t('web.sync.author_load_more') }}</span>
        <span v-else-if="authors.length">{{ t('web.sync.author_all_loaded', { n: authorTotal }) }}</span>
        <span v-else>{{ t('web.sync.no_authors') }}</span>
      </div>
    </div>

    <!-- Fullscreen 30-day chart (dysync: 近30天同步曲线图) -->
    <el-dialog v-model="fullVisible" :title="t('web.sync.trend_30days')" width="80%" destroy-on-close @opened="loadFullTrend">
      <div class="full-chart-box">
        <svg v-if="fullTrend.length" :viewBox="`0 0 ${CW} ${CH + 20}`" preserveAspectRatio="none" class="trend-svg">
          <line v-for="g in fullGridYs" :key="g" :x1="padL" :x2="CW - padR" :y1="g" :y2="g" class="grid-line" />
          <template v-for="(s, si) in series" :key="s.key">
            <polyline :points="fullStackPoints(si)" class="trend-line" :style="{ stroke: s.color }" />
          </template>
          <text v-for="(d, i) in fullTrend" :key="d.date" :x="fullXPos(i)" :y="CH + 14" class="axis-label" text-anchor="middle">
            {{ i % 3 === 0 ? d.date.slice(5) : '' }}
          </text>
        </svg>
        <el-empty v-else :description="t('web.sync.no_trend')" :image-size="60" />
      </div>
      <div class="legend">
        <span v-for="s in series" :key="s.key" class="legend-item">
          <i :style="{ background: s.color }"></i>{{ t(s.labelKey) }}
        </span>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Star, FolderOpened, VideoCamera, Bell, FullScreen, Loading } from '@element-plus/icons-vue'
import { getStatistics, getTrendStats, getAuthorStats, deleteAuthorRecords } from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()

const KINDS = [
  { key: 'liked', countKey: 'liked_count', sizeKey: 'liked_size', labelKey: 'web.sync.stat_liked', icon: Star, cls: 'ic-like' },
  { key: 'favorites', countKey: 'favorites_count', sizeKey: 'favorites_size', labelKey: 'web.sync.stat_favorites', icon: Collection, cls: 'ic-fav' },
  { key: 'playlist', countKey: 'playlist_count', sizeKey: 'playlist_size', labelKey: 'web.sync.stat_playlist', icon: FolderOpened, cls: 'ic-playlist' },
  { key: 'channel', countKey: 'channel_count', sizeKey: 'channel_size', labelKey: 'web.sync.stat_channel', icon: VideoCamera, cls: 'ic-channel' },
  { key: 'subscriptions', countKey: 'subs_count', sizeKey: 'subs_size', labelKey: 'web.sync.stat_subs', icon: Bell, cls: 'ic-subs' },
]

const series = [
  { key: 'liked', labelKey: 'web.sync.stat_liked', color: '#5470c6' },
  { key: 'favorites', labelKey: 'web.sync.stat_favorites', color: '#73c0de' },
  { key: 'playlist', labelKey: 'web.sync.stat_playlist', color: '#91cc75' },
  { key: 'channel', labelKey: 'web.sync.stat_channel', color: '#fac858' },
  { key: 'subscriptions', labelKey: 'web.sync.stat_subs', color: '#ee6666' },
]

const st = ref({})
const trend = ref([])
const fullTrend = ref([])
const fullVisible = ref(false)

// SVG chart geometry
const CW = 600
const CH = 220
const padL = 30
const padR = 12
const padT = 14
const padB = 26

function fmtGB(bytes) {
  return ((Number(bytes) || 0) / (1024 ** 3)).toFixed(2)
}

function maxTotal(rows) {
  return Math.max(1, ...rows.map((r) => r.total))
}

function xPos(i) {
  const n = trend.value.length
  if (n <= 1) return padL + (CW - padL - padR) / 2
  return padL + (i * (CW - padL - padR)) / (n - 1)
}
function fullXPos(i) {
  const n = fullTrend.value.length
  if (n <= 1) return padL + (CW - padL - padR) / 2
  return padL + (i * (CW - padL - padR)) / (n - 1)
}
function yPos(v, max) {
  return padT + (1 - v / max) * (CH - padT - padB)
}

// Stacked cumulative lines (dysync stack:'Total')
function stackPoints(si) {
  const max = maxTotal(trend.value)
  return trend.value
    .map((r, i) => {
      let acc = 0
      for (let k = 0; k <= si; k++) acc += r[series[k].key] || 0
      return `${xPos(i)},${yPos(acc, max)}`
    })
    .join(' ')
}
function fullStackPoints(si) {
  const max = maxTotal(fullTrend.value)
  return fullTrend.value
    .map((r, i) => {
      let acc = 0
      for (let k = 0; k <= si; k++) acc += r[series[k].key] || 0
      return `${fullXPos(i)},${yPos(acc, max)}`
    })
    .join(' ')
}

const gridYs = computed(() => [0.25, 0.5, 0.75].map((f) => padT + f * (CH - padT - padB)))
const fullGridYs = gridYs

// ---- authors (infinite scroll like dysync) ----
const authors = ref([])
const authorTotal = ref(0)
const authorPage = ref(0)
const authorLoading = ref(false)
const authorHasMore = ref(true)
const loadMoreRef = ref(null)
let observer = null
const AUTHOR_PAGE_SIZE = 30

function pct(count) {
  const total = st.value.total_videos || 0
  return total > 0 ? Math.min(100, (count / total) * 100) : 0
}

async function loadAuthors(reset = false) {
  if (authorLoading.value || (!reset && !authorHasMore.value)) return
  const nextPage = reset ? 1 : authorPage.value + 1
  authorLoading.value = true
  try {
    const d = await getAuthorStats(nextPage, AUTHOR_PAGE_SIZE)
    const pageAuthors = d.authors || []
    authors.value = reset ? pageAuthors : [...authors.value, ...pageAuthors]
    authorPage.value = nextPage
    authorTotal.value = d.total ?? authors.value.length
    authorHasMore.value = authors.value.length < authorTotal.value
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    authorLoading.value = false
  }
}

async function deleteAuthor(a) {
  try {
    await ElMessageBox.confirm(
      t('web.sync.author_delete_confirm', { name: a.channel }),
      t('web.sync.delete'),
      { type: 'warning', confirmButtonText: t('web.sync.delete'), cancelButtonText: t('web.sync.cancel') },
    )
  } catch {
    return
  }
  try {
    const r = await deleteAuthorRecords(a.channel)
    ElMessage.success(t('web.sync.author_deleted', { n: r.removed }))
    await Promise.all([loadStats(), loadAuthors(true)])
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

async function loadStats() {
  try {
    st.value = await getStatistics()
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

async function loadTrend() {
  try {
    trend.value = (await getTrendStats(7)).trend || []
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

function openFullChart() {
  fullVisible.value = true
}

async function loadFullTrend() {
  try {
    fullTrend.value = (await getTrendStats(30)).trend || []
  } catch (e) {
    ElMessage.error(errText(e))
  }
}

onMounted(async () => {
  await Promise.all([loadStats(), loadTrend(), loadAuthors(true)])
  await nextTick()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) loadAuthors()
    },
    { rootMargin: '240px 0px' },
  )
  if (loadMoreRef.value) observer.observe(loadMoreRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<style scoped>
.dash-page { display: flex; flex-direction: column; gap: 14px; }
.dash-top { display: grid; grid-template-columns: 4fr 6fr; gap: 14px; }
@media (max-width: 992px) { .dash-top { grid-template-columns: 1fr; } }

.stats-left { padding: 16px 20px; display: flex; flex-direction: column; }
.stat-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.main-stat { display: flex; flex-direction: column; gap: 4px; }
.stat-meta { font-size: 12px; color: var(--yts-text-dim); letter-spacing: 0.5px; }
.stat-value { font-size: 28px; font-weight: 700; color: var(--yts-text); display: flex; align-items: baseline; gap: 4px; }
.unit { font-size: 14px; color: var(--yts-text-dim); }
.stat-subitems { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; border-top: 1px solid var(--yts-border); padding-top: 10px; flex: 1; }
.subitem { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--yts-border); border-radius: 8px; }
.subitem-icon { width: 24px; height: 24px; border-radius: 6px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ic-like { background: rgba(233, 30, 99, 0.15); color: #e91e63; }
.ic-fav { background: rgba(255, 193, 7, 0.15); color: #ffc107; }
.ic-playlist { background: rgba(255, 152, 0, 0.15); color: #ff9800; }
.ic-channel { background: rgba(156, 39, 176, 0.15); color: #ba68c8; }
.ic-subs { background: rgba(63, 81, 181, 0.15); color: #7986cb; }
.subitem-meta { font-size: 12px; color: var(--yts-text-dim); flex: 1; }
.subitem-value { font-size: 13px; font-weight: 600; color: var(--yts-text); }
.split { font-size: 11px; color: var(--yts-text-dim); }

.chart-right { padding: 14px 16px; display: flex; flex-direction: column; }
.chart-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.chart-title { font-size: 14px; font-weight: 600; color: var(--yts-text); }
.chart-box { flex: 1; min-height: 220px; }
.trend-svg { width: 100%; height: 100%; min-height: 210px; }
.grid-line { stroke: var(--yts-border); stroke-width: 1; stroke-dasharray: 3 3; }
.trend-line { fill: none; stroke-width: 2; }
.axis-label { font-size: 10px; fill: var(--yts-text-dim); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; padding-top: 8px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--yts-text-dim); }
.legend-item i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

.authors-card { padding: 16px; }
.authors-head { display: flex; align-items: center; gap: 16px; margin-bottom: 14px; }
.section-title { margin: 0; font-size: 16px; font-weight: 600; color: var(--yts-text); }
.hint { font-size: 12px; color: var(--yts-text-dim); }
.authors-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
@media (max-width: 1200px) { .authors-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .authors-grid { grid-template-columns: repeat(2, 1fr); } }
.author-card { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--yts-border); border-radius: 8px; cursor: default; transition: transform 0.15s ease; }
.author-card:hover { transform: translateY(-2px); border-color: var(--yts-primary); }
.author-row { display: flex; align-items: center; gap: 10px; }
.author-avatar { width: 40px; height: 40px; border-radius: 50%; background: rgba(201, 0, 0, 0.25); color: #ff8a8a; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.author-info { flex: 1; min-width: 0; }
.author-name { font-size: 14px; color: var(--yts-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.author-stats { font-size: 11px; color: var(--yts-text-dim); margin-top: 2px; }
.author-progress { height: 5px; background: var(--yts-border); border-radius: 3px; overflow: hidden; }
.progress-bar { height: 100%; background: #4caf50; border-radius: 3px; transition: width 0.4s ease; }
.load-more { display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; margin-top: 10px; color: var(--yts-text-dim); font-size: 12px; }

.full-chart-box { height: 400px; }
.full-chart-box .trend-svg { height: 380px; }
</style>
