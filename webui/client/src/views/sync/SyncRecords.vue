<template>
  <div class="records-page">
    <div class="yts-card">
      <div class="toolbar">
        <el-input v-model="q" size="small" style="width: 200px" clearable :placeholder="t('web.sync.search_ph')" @input="debouncedLoad" />
        <el-select v-model="status" size="small" style="width: 120px" clearable :placeholder="t('web.sync.col_status')" @change="reload">
          <el-option v-for="s in STATUS_OPTS" :key="s" :label="statusLabel(s)" :value="s" />
        </el-select>
        <el-select v-model="kind" size="small" style="width: 130px" clearable :placeholder="t('web.sync.filter_type')" @change="reload">
          <el-option v-for="k in KIND_OPTS" :key="k" :label="kindLabel(k)" :value="k" />
        </el-select>
        <el-select v-model="channel" size="small" style="width: 160px" clearable filterable :placeholder="t('web.sync.filter_channel')" @change="reload">
          <el-option v-for="c in channels" :key="c" :label="c" :value="c" />
        </el-select>
        <el-date-picker v-model="dateRange" size="small" type="daterange" value-format="X" style="width: 230px"
          :start-placeholder="t('web.sync.filter_date')" :end-placeholder="t('web.sync.filter_date')" @change="reload" />
        <span class="count">{{ t('web.sync.entries_count', { count: total }) }}</span>
        <div class="spacer" />
        <el-button size="small" :icon="Delete" @click="deletedDrawer = true">{{ t('web.sync.deleted_drawer') }}</el-button>
        <el-button size="small" :loading="scanning" @click="scanMissing">{{ t('web.sync.scan_missing') }}</el-button>
      </div>

      <div v-if="sel.size" class="selbar">
        <el-button size="small" type="success" :loading="busy" @click="resyncSel">{{ t('web.sync.batch_redownload', { n: sel.size }) }}</el-button>
        <el-button size="small" :loading="busy" @click="softDeleteSel">{{ t('web.sync.batch_delete', { n: sel.size }) }}</el-button>
        <el-button size="small" type="warning" :loading="busy" @click="nfoSel">{{ t('web.sync.nfo_generate') }}</el-button>
        <el-popover placement="bottom" :width="240" trigger="click">
          <template #reference><el-button size="small" type="danger">{{ t('web.sync.permanent_delete', { n: sel.size }) }}</el-button></template>
          <el-checkbox v-model="permDeleteFiles">{{ t('web.sync.also_delete_files') }}</el-checkbox>
          <div style="margin-top:8px"><el-button size="small" type="danger" :loading="busy" @click="permanentDeleteSel">{{ t('web.sync.permanent_delete', { n: sel.size }) }}</el-button></div>
        </el-popover>
        <el-button size="small" @click="clearSel">{{ t('web.sync.cancel_sel') }}</el-button>
      </div>

      <el-table :data="rows" size="small" stripe v-loading="loading" @selection-change="onSelChange">
        <el-table-column type="selection" width="40" />
        <el-table-column :label="t('web.sync.col_thumb')" width="76">
          <template #default="{ row }">
            <img v-if="row.thumbnail_url" class="thumb" :src="thumb(row.thumbnail_url)" loading="lazy" @error="onImgErr(row)" />
            <div v-else class="thumb ph"></div>
          </template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_video')" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <a v-if="row.url" :href="row.url" target="_blank" class="vlink">{{ row.video_title || t('web.sync.unknown') }}</a>
            <span v-else>{{ row.video_title || t('web.sync.unknown') }}</span>
            <div class="sub">{{ row.video_id }} · {{ row.channel || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_status')" width="90" align="center">
          <template #default="{ row }"><el-tag size="small" :type="tagType(row.status)">{{ statusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_kind')" width="90" align="center">
          <template #default="{ row }"><span class="dim">{{ kindLabel(row.kind) }}</span></template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_size')" width="90" align="center">
          <template #default="{ row }"><span class="dim">{{ row.size ? fmtSize(row.size) : '-' }}</span></template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_sync_at')" width="150" align="center">
          <template #default="{ row }">{{ fmtTime(row.last_sync) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_ops')" width="230" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :disabled="!row.file_path" @click="play(row)">{{ t('web.sync.play') }}</el-button>
            <el-button link size="small" :disabled="!row.file_path" @click="copyPath(row)">{{ t('web.sync.copy_path') }}</el-button>
            <el-button link size="small" @click="share(row)">{{ t('web.sync.share_link') }}</el-button>
            <el-button link type="danger" size="small" @click="exclude(row)">{{ t('web.sync.exclude') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total"
        layout="prev, pager, next" background small style="margin-top: 12px; justify-content: center" @current-change="load" />
      <el-empty v-if="!loading && !rows.length" :description="t('web.sync.no_records')" :image-size="70" />
    </div>

    <!-- Excludes list -->
    <div class="yts-card">
      <div class="head">
        <h3>{{ t('web.sync.excludes') }}</h3>
        <el-button v-if="missingCount" size="small" type="warning" :loading="busy" @click="removeMissing">{{ t('web.sync.remove_missing') }} ({{ missingCount }})</el-button>
      </div>
      <el-tag v-for="e in excludes" :key="e.video_id" closable class="ex-tag" @close="unexclude(e)">{{ e.video_id }}</el-tag>
      <el-empty v-if="!excludes.length" :description="t('web.sync.no_excludes')" :image-size="50" />
    </div>

    <!-- Deleted records drawer -->
    <el-drawer v-model="deletedDrawer" :title="t('web.sync.deleted_drawer')" size="520px" @open="loadDeleted">
      <el-table :data="deleted" size="small" v-loading="deletedLoading">
        <el-table-column :label="t('web.sync.col_video')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.video_title || row.video_id }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.deleted_at')" width="150" align="center">
          <template #default="{ row }">{{ fmtTime(row.deleted_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_ops')" width="80" align="center">
          <template #default="{ row }"><el-button link type="primary" size="small" @click="restore(row)">{{ t('web.sync.restore') }}</el-button></template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!deletedLoading && !deleted.length" :description="t('web.sync.no_deleted')" :image-size="60" />
    </el-drawer>

    <VideoPlayerDialog v-model="playerVisible" :record="playerRecord" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import {
  listRecords, resyncRecords, addExclude, listExcludes, removeExclude,
  listRecordChannels, batchRedownloadRecords, batchDeleteRecords,
  permanentDeleteRecords, createShareLink, generateNFOBatch,
  scanMissingRecords, removeMissingRecords, getDeletedRecords, restoreRecord,
} from '@/api/sync'
import { errText } from '@/api/http'
import { useReveal } from '@/composables/useReveal'
import VideoPlayerDialog from './VideoPlayerDialog.vue'

const { t } = useI18n()
const { reveal } = useReveal()

const STATUS_OPTS = ['downloaded', 'queued', 'running', 'failed', 'excluded', 'missing']
const KIND_OPTS = ['liked', 'favorites', 'playlist', 'channel', 'subscriptions']

const rows = ref([])
const excludes = ref([])
const channels = ref([])
const q = ref('')
const status = ref('')
const kind = ref('')
const channel = ref('')
const dateRange = ref(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const loading = ref(false)
const busy = ref(false)
const scanning = ref(false)
const missingCount = ref(0)
const sel = ref(new Set())
const selRows = ref([])
const permDeleteFiles = ref(false)
let timer = null

const deletedDrawer = ref(false)
const deleted = ref([])
const deletedLoading = ref(false)

const playerVisible = ref(false)
const playerRecord = ref(null)

function statusLabel(s) { return t(`web.sync.status_${s}`) || s }
function kindLabel(k) { return k ? t(`web.sync.kind_${k === 'subscriptions' ? 'subs' : k}`) : '-' }
function tagType(s) {
  return { downloaded: 'success', running: 'primary', queued: 'warning', failed: 'danger', excluded: 'info', missing: 'danger' }[s] || 'info'
}
function thumb(url) { return `/api/thumbnail?url=${encodeURIComponent(url)}` }
function onImgErr(row) { row.thumbnail_url = '' }
function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '-' }
function fmtSize(bytes) {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++ }
  return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, limit: pageSize.value, q: q.value || undefined, status: status.value || undefined, kind: kind.value || undefined, channel: channel.value || undefined }
    if (dateRange.value && dateRange.value.length === 2) {
      params.date_from = Number(dateRange.value[0])
      params.date_to = Number(dateRange.value[1]) + 86399
    }
    const d = await listRecords(params)
    rows.value = d.entries || []
    total.value = d.total || 0
  } catch (e) { ElMessage.error(errText(e)) } finally { loading.value = false }
}

function reload() { page.value = 1; load() }
function debouncedLoad() { clearTimeout(timer); timer = setTimeout(reload, 350) }

function onSelChange(selection) {
  selRows.value = selection
  sel.value = new Set(selection.map((r) => r.id))
}
function clearSel() { sel.value = new Set(); selRows.value = [] }

async function resyncSel() {
  const ids = [...sel.value]
  if (!ids.length) return
  busy.value = true
  try { const r = await batchRedownloadRecords(ids); ElMessage.success(t('web.sync.resync_done', { n: r.requeued })); clearSel(); load() }
  catch (e) { ElMessage.error(errText(e)) } finally { busy.value = false }
}

async function softDeleteSel() {
  const ids = [...sel.value]
  if (!ids.length) return
  busy.value = true
  try { const r = await batchDeleteRecords(ids); ElMessage.success(t('web.sync.batch_deleted', { n: r.removed })); clearSel(); load() }
  catch (e) { ElMessage.error(errText(e)) } finally { busy.value = false }
}

async function permanentDeleteSel() {
  const ids = [...sel.value]
  if (!ids.length) return
  try { await ElMessageBox.confirm(t('web.sync.permanent_delete_confirm', { n: ids.length }), t('web.sync.permanent_delete'), { type: 'warning' }) } catch { return }
  busy.value = true
  try { const r = await permanentDeleteRecords(ids, permDeleteFiles.value, true); ElMessage.success(t('web.sync.permanent_deleted', { n: r.removed })); clearSel(); load(); loadExcludes() }
  catch (e) { ElMessage.error(errText(e)) } finally { busy.value = false }
}

async function nfoSel() {
  const vids = selRows.value.map((r) => r.video_id).filter(Boolean)
  if (!vids.length) return
  busy.value = true
  try { const r = await generateNFOBatch(vids); ElMessage.success(t('web.sync.nfo_batch_done', { ok: r.success, fail: r.failed })) }
  catch (e) { ElMessage.error(errText(e)) } finally { busy.value = false }
}

async function scanMissing() {
  scanning.value = true
  try { const r = await scanMissingRecords(); missingCount.value = r.missing; ElMessage.success(t('web.sync.scan_missing_done', { n: r.missing })); load() }
  catch (e) { ElMessage.error(errText(e)) } finally { scanning.value = false }
}

async function removeMissing() {
  try { await ElMessageBox.confirm(t('web.sync.remove_missing_confirm'), t('web.sync.remove_missing'), { type: 'warning' }) } catch { return }
  busy.value = true
  try { const r = await removeMissingRecords(false); ElMessage.success(t('web.sync.remove_missing_done', { n: r.removed })); missingCount.value = 0; load() }
  catch (e) { ElMessage.error(errText(e)) } finally { busy.value = false }
}

function play(row) { playerRecord.value = row; playerVisible.value = true }

async function copyPath(row) {
  if (!row.file_path) { ElMessage.warning(t('web.sync.path_missing')); return }
  try { await navigator.clipboard.writeText(row.file_path); ElMessage.success(t('web.sync.copy_ok')) }
  catch { reveal(row.file_path) }
}

async function share(row) {
  try {
    const r = await createShareLink(row.video_id)
    const url = `${window.location.origin}${r.url}`
    try { await navigator.clipboard.writeText(url); ElMessage.success(t('web.sync.share_copied')) }
    catch { await ElMessageBox.alert(url, t('web.sync.share_link')) }
  } catch (e) {
    const detail = e?.response?.data?.detail || ''
    ElMessage.warning(detail.includes('disabled') ? t('web.sync.share_disabled') : errText(e))
  }
}

async function exclude(row) {
  try { await ElMessageBox.confirm(t('web.sync.exclude_confirm', { n: row.video_id }), t('web.sync.exclude'), { type: 'warning' }) } catch { return }
  try { await addExclude(row.video_id, 'manual'); ElMessage.success(t('web.sync.excluded_ok')); loadExcludes(); load() } catch (e) { ElMessage.error(errText(e)) }
}

async function loadExcludes() { excludes.value = (await listExcludes()).excludes || [] }
async function unexclude(e) {
  try { await removeExclude(e.video_id); loadExcludes() } catch (err) { ElMessage.error(errText(err)) }
}

async function loadDeleted() {
  deletedLoading.value = true
  try { deleted.value = (await getDeletedRecords(1, 100)).entries || [] }
  catch (e) { ElMessage.error(errText(e)) } finally { deletedLoading.value = false }
}

async function restore(row) {
  try { await ElMessageBox.confirm(t('web.sync.restore_confirm'), t('web.sync.restore'), { type: 'warning' }) } catch { return }
  try { await restoreRecord(row.video_id); ElMessage.success(t('web.sync.restored')); loadDeleted(); load() } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(async () => {
  load()
  loadExcludes()
  try { channels.value = (await listRecordChannels()).channels || [] } catch { /* ignore */ }
})
</script>

<style scoped>
.records-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.toolbar .count { color: var(--yts-text-dim); font-size: 13px; }
.toolbar .spacer { flex: 1; }
.selbar { display: flex; gap: 8px; align-items: center; padding: 8px 10px; background: rgba(201,0,0,0.08); border-radius: 8px; margin-bottom: 10px; }
.thumb { width: 60px; height: 34px; object-fit: cover; border-radius: 4px; display: block; }
.thumb.ph { background: rgba(255,255,255,0.06); }
.vlink { color: var(--yts-primary, #ff6b6b); text-decoration: none; }
.vlink:hover { text-decoration: underline; }
.sub { font-size: 11px; color: var(--yts-text-dim); margin-top: 2px; }
.dim { color: var(--yts-text-dim); font-size: 12px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.head h3 { margin: 0; }
.ex-tag { margin: 0 8px 8px 0; }
</style>
