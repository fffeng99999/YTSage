<template>
  <!--
    dysync parity: 支持移动端.
    A phone-sized view of the sync centre: status, one-tap "sync all",
    recent runs and the newest records (tap to play).
  -->
  <div class="m-sync">
    <div class="m-head">
      <h3>{{ t('web.sync.title') }} · {{ t('web.sync.mobile') }}</h3>
      <el-button size="small" circle :icon="Refresh" @click="load" />
    </div>

    <div class="m-cards">
      <div class="m-card">
        <div class="m-num">{{ status.profile_count || 0 }}</div>
        <div class="m-lab">{{ t('web.sync.stat_profiles') }}</div>
      </div>
      <div class="m-card">
        <div class="m-num">{{ status.record_count || 0 }}</div>
        <div class="m-lab">{{ t('web.sync.stat_records') }}</div>
      </div>
      <div class="m-card m-wide" :class="{ 'm-on': busy }">
        <div class="m-num">{{ busy ? t('web.sync.running') : t('web.sync.idle') }}</div>
        <div class="m-lab">{{ t('web.sync.stat_sync_state') }}</div>
      </div>
    </div>

    <el-button class="m-syncall" type="primary" size="large" :loading="syncing" @click="syncAll">
      {{ t('web.sync.sync_all') }}
    </el-button>

    <div class="m-sec">{{ t('web.sync.recent_runs') }}</div>
    <div v-if="!runs.length" class="m-empty">{{ t('web.sync.no_records') }}</div>
    <div v-for="r in runs" :key="r.id" class="m-row">
      <div class="m-row-main">
        <div class="m-row-title">{{ r.profile_name || ('#' + r.profile_id) }}</div>
        <div class="m-row-sub">{{ fmt(r.started_at) }} · {{ r.summary || '' }}</div>
      </div>
      <div class="m-row-right">
        <span class="m-pill m-pill-ok">+{{ r.new_count || 0 }}</span>
        <span v-if="r.failed_count" class="m-pill m-pill-bad">{{ r.failed_count }}</span>
      </div>
    </div>

    <div class="m-sec">{{ t('web.sync.records') }}</div>
    <div v-if="!records.length" class="m-empty">{{ t('web.sync.no_records') }}</div>
    <div v-for="rec in records" :key="rec.id" class="m-rec" @click="play(rec)">
      <img v-if="rec.thumbnail_url" class="m-thumb" :src="thumb(rec)" alt="" />
      <div class="m-rec-main">
        <div class="m-rec-title">{{ rec.video_title || rec.video_id }}</div>
        <div class="m-row-sub">{{ rec.channel || '' }}</div>
      </div>
      <span class="m-pill" :class="pillCls(rec.status)">{{ rec.status }}</span>
    </div>

    <el-dialog v-model="player.visible" :title="player.title" width="96%" top="4vh">
      <video v-if="player.url" :src="player.url" controls autoplay style="width:100%" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { syncStatus, latestRuns, listRecords, runSync, getVideoStreamUrl } from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()

const status = ref({})
const runs = ref([])
const records = ref([])
const profiles = ref([])
const syncing = ref(false)
const busy = ref(false)
const player = reactive({ visible: false, url: '', title: '' })

function fmt(ts) {
  if (!ts) return ''
  const d = new Date(Number(ts) * 1000)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

function thumb(rec) {
  // Route through the public thumbnail proxy (works for remote hosts too).
  return `/api/thumbnail?url=${encodeURIComponent(rec.thumbnail_url || '')}`
}

function pillCls(s) {
  return { downloaded: 'm-pill-ok', failed: 'm-pill-bad' }[s] || ''
}

async function load() {
  try {
    status.value = await syncStatus()
    busy.value = !!status.value.running
  } catch (e) {
    ElMessage.error(errText(e))
  }
  try {
    runs.value = (await latestRuns()).runs || []
  } catch {
    runs.value = []
  }
  try {
    const r = await listRecords({ page: 1, limit: 20 })
    records.value = r.entries || r.records || []
  } catch {
    records.value = []
  }
}

async function syncAll() {
  if (!profiles.value.length) {
    try {
      const s = await syncStatus()
      profiles.value = s.profiles || []
    } catch {
      /* ignore */
    }
  }
  if (!profiles.value.length) {
    ElMessage.info(t('web.sync.no_profiles'))
    return
  }
  syncing.value = true
  busy.value = true
  let n = 0
  try {
    for (const p of profiles.value) {
      if (p.enabled === false) continue
      const r = await runSync(p.id)
      n += r.new || 0
    }
    ElMessage.success(t('web.sync.sync_all_done'))
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    syncing.value = false
    busy.value = false
    void n
    load()
  }
}

function play(rec) {
  player.title = rec.video_title || rec.video_id || ''
  player.url = getVideoStreamUrl(rec.video_id)
  player.visible = true
}

onMounted(load)
</script>

<style scoped>
.m-sync { padding: 10px 12px 24px; }
.m-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.m-head h3 { margin: 0; font-size: 16px; }
.m-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.m-card {
  border: 1px solid var(--yts-border); border-radius: 10px; padding: 12px; text-align: center;
  background: var(--yts-bg-soft, rgba(255, 255, 255, 0.03));
}
.m-wide { grid-column: 1 / -1; }
.m-num { font-size: 20px; font-weight: 600; word-break: break-word; }
.m-on .m-num { color: #67c23a; }
.m-lab { font-size: 12px; color: var(--yts-text-dim); margin-top: 4px; }
.m-syncall { width: 100%; margin: 14px 0 18px; }
.m-sec { font-size: 13px; font-weight: 600; margin: 14px 0 8px; color: var(--yts-text-dim); }
.m-empty { font-size: 13px; color: var(--yts-text-dim); padding: 10px 0; }
.m-row, .m-rec {
  display: flex; align-items: center; gap: 10px; padding: 10px;
  border: 1px solid var(--yts-border); border-radius: 10px; margin-bottom: 8px;
}
.m-row-main, .m-rec-main { flex: 1; min-width: 0; }
.m-row-title, .m-rec-title { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-row-sub { font-size: 12px; color: var(--yts-text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-row-right { display: flex; gap: 6px; }
.m-thumb { width: 88px; height: 50px; object-fit: cover; border-radius: 6px; flex: none; }
.m-pill {
  font-size: 11px; padding: 2px 7px; border-radius: 10px;
  border: 1px solid var(--yts-border); color: var(--yts-text-dim); flex: none;
}
.m-pill-ok { border-color: #67c23a; color: #67c23a; }
.m-pill-bad { border-color: #f56c6c; color: #f56c6c; }
</style>
