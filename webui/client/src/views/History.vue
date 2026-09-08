<template>
  <div class="history-page">
    <div class="yts-card toolbar-card">
      <div class="yts-card-title">{{ t('history.title') }}</div>
      <div class="toolbar">
        <el-input
          v-model="query"
          :placeholder="t('history.search_placeholder')"
          clearable
          size="small"
          style="width: 280px"
          @input="debouncedLoad"
        />
        <span class="count">{{ t('history.entries_count', { count: total }) }}</span>
        <el-button size="small" type="danger" @click="clearAll" :disabled="!entries.length">
          {{ t('history.clear_all') }}
        </el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !entries.length" :description="t('history.no_history_description')" />

    <div v-loading="loading" class="cards">
      <div v-for="e in entries" :key="e.id" class="hist-card yts-card">
        <div class="thumb">
          <img v-if="e.thumbnail_url" :src="`/api/thumbnail?url=${encodeURIComponent(e.thumbnail_url)}`" loading="lazy" @error="onImgErr(e)" />
          <div v-else class="thumb-ph">{{ e.is_audio_only ? '🎵' : '📹' }}</div>
        </div>
        <div class="body">
          <div class="title-row">
            <span class="title" :title="e.title">{{ e.title }}</span>
            <el-tag size="small" :type="e.is_audio_only ? 'primary' : 'danger'">
              {{ e.is_audio_only ? t('history.audio_download') : t('history.video_download') }}
            </el-tag>
          </div>
          <p class="meta">{{ e.channel || t('video_info.unknown_channel') }} · {{ t('history.downloaded_on') }} {{ fmtDate(e.download_date) }}</p>
          <p class="meta">{{ fmtSize(e.file_size) }}<span v-if="e.resolution"> · {{ e.resolution }}</span></p>
        </div>
        <div class="ops">
          <el-button
            size="small"
            text
            :title="local ? t('history.open_location') : t('web.env.download_file')"
            @click="openLocation(e)"
          >{{ local ? '📁' : '⬇️' }}</el-button>
          <el-button size="small" text @click="redownload(e)" :title="t('history.redownload')">⬇️</el-button>
          <el-button size="small" text @click="removeEntry(e)" :title="t('history.remove')">🗑️</el-button>
        </div>
      </div>
    </div>

    <!-- Server-side pagination (module 6.1): SQLite LIMIT/OFFSET -->
    <div v-if="total > pageSize" class="pager-row">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        :pager-count="7"
        layout="prev, pager, next, jumper"
        background
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listHistoryPage, deleteHistory, clearHistory } from '@/api/history'
import { errText } from '@/api/http'
import { useReveal } from '@/composables/useReveal'

const { t } = useI18n()
const router = useRouter()
const { local, reveal, directDownload } = useReveal()

const entries = ref([])
const query = ref('')
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
let timer = null

async function load() {
  loading.value = true
  try {
    const data = await listHistoryPage(page.value, pageSize.value, query.value.trim() || undefined)
    entries.value = data.entries || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loading.value = false
  }
}

function debouncedLoad() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 350)
}

function fmtDate(d) {
  if (!d) return ''
  try {
    return new Date(d).toLocaleString()
  } catch {
    return d
  }
}

function fmtSize(b) {
  if (!b) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${units[i]}`
}

function onImgErr(e) {
  e.thumbnail_url = ''
}

async function openLocation(e) {
  // Remote: stream the file to the browser instead of popping the server's explorer
  if (!local) {
    if (!e.file_path) { ElMessage.warning(t('history.file_not_found')); return }
    directDownload(e.file_path)
    return
  }
  await reveal(e.file_path)
}

async function redownload(e) {
  if (!e.url) {
    ElMessage.error(t('history.no_url_error'))
    return
  }
  try {
    await ElMessageBox.confirm(t('history.redownload_confirm_message'), t('history.redownload_confirm_title'), { type: 'warning' })
  } catch { return }
  router.push({
    path: '/',
    query: { url: e.url, opts: JSON.stringify(e.download_options || {}) },
  })
}

async function removeEntry(e) {
  try {
    await ElMessageBox.confirm(t('history.remove_confirm_message'), t('history.remove_confirm_title'), { type: 'warning' })
  } catch { return }
  await deleteHistory(e.id)
  ElMessage.success(t('history.item_removed'))
  load()
}

async function clearAll() {
  try {
    await ElMessageBox.confirm(t('history.clear_confirm_message'), t('history.clear_confirm_title'), { type: 'warning' })
  } catch { return }
  await clearHistory()
  ElMessage.success(t('history.history_cleared'))
  page.value = 1
  load()
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; }
.toolbar .count { color: var(--yts-text-dim); font-size: 13px; margin-left: auto; }
.cards { display: flex; flex-direction: column; gap: 12px; }
.hist-card { display: flex; gap: 14px; align-items: center; margin-bottom: 0; padding: 12px; }
.thumb { flex: 0 0 160px; height: 90px; border-radius: 6px; overflow: hidden; background: #101214; display: flex; align-items: center; justify-content: center; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-ph { font-size: 32px; opacity: 0.5; }
.body { flex: 1; min-width: 0; }
.title-row { display: flex; gap: 8px; align-items: center; }
.title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { margin: 4px 0 0; color: var(--yts-text-dim); font-size: 12px; }
.ops { display: flex; flex-direction: column; gap: 2px; }
.pager-row { margin-top: 12px; display: flex; justify-content: center; }
</style>
