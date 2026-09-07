<template>
  <div class="jobs-page">
    <div class="yts-card toolbar-card">
      <el-input v-model="filter" :placeholder="t('history.search_placeholder')" clearable size="small" style="width: 280px" />
      <el-button size="small" @click="store.fetchJobs">{{ t('about.refresh') }}</el-button>
      <span class="count">{{ store.jobs.length }}</span>
    </div>

    <el-empty v-if="!filtered.length" :description="t('history.no_history')" />

    <div v-for="j in filtered" :key="j.job_id" class="job-card yts-card">
      <div class="job-head">
        <span class="fname">{{ j.current_filename || j.title || j.url }}</span>
        <el-tag size="small" :type="statusTag(j.status)">{{ statusLabel(j.status) }}</el-tag>
      </div>
      <el-progress :percentage="Math.min(100, j.progress || 0)" :stroke-width="12" :status="progStatus(j.status)" />
      <div class="job-meta">
        <span>{{ j.url }}</span>
      </div>
      <div class="job-meta dim">
        <span v-if="j.speed">{{ t('download.speed') }}: {{ j.speed }}</span>
        <span v-if="j.eta">{{ t('download.eta') }}: {{ j.eta }}</span>
        <span v-if="j.error">{{ j.error_key ? t(j.error_key, { error: j.error }) : j.error }}</span>
      </div>
      <div class="job-ops">
        <el-button v-if="j.status === 'running'" size="small" @click="pause(j)">{{ t('buttons.pause') }}</el-button>
        <el-button v-if="j.status === 'paused'" size="small" type="warning" @click="resume(j)">{{ t('buttons.resume') }}</el-button>
        <el-button v-if="['running','paused','pending','queued'].includes(j.status)" size="small" type="danger" @click="cancel(j)">{{ t('buttons.cancel') }}</el-button>
        <el-button v-if="j.status === 'completed' && j.last_file_path" size="small" @click="reveal(j.last_file_path)">📁</el-button>
        <el-button v-if="!['running','pending','queued'].includes(j.status)" size="small" text @click="remove(j)">{{ t('history.remove') }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDownloadStore } from '@/stores/download'
import { pauseJob, resumeJob, cancelJob, removeJob } from '@/api/download'
import { errText } from '@/api/http'
import { useReveal } from '@/composables/useReveal'

const { t } = useI18n()
const store = useDownloadStore()
const { reveal } = useReveal()
const filter = ref('')

const filtered = computed(() => {
  const f = filter.value.trim().toLowerCase()
  if (!f) return store.jobs
  return store.jobs.filter((j) =>
    (j.current_filename || '').toLowerCase().includes(f) ||
    (j.url || '').toLowerCase().includes(f) ||
    (j.title || '').toLowerCase().includes(f)
  )
})

function statusTag(s) {
  return { completed: 'success', error: 'danger', cancelled: 'info', paused: 'warning', running: 'primary', queued: 'info' }[s] || 'info'
}
function statusLabel(s) {
  return {
    running: t('download.downloading'), paused: t('download.paused'),
    completed: t('download.completed'), cancelled: t('download.cancelled'),
    error: t('main_ui.error_title'), pending: t('download.starting'),
    queued: t('web.batch.queued'),
  }[s] || s
}
function progStatus(s) {
  if (s === 'completed') return 'success'
  if (s === 'error' || s === 'cancelled') return 'exception'
  return ''
}

async function pause(j) { try { await pauseJob(j.job_id) } catch (e) { ElMessage.error(errText(e)) } }
async function resume(j) { try { await resumeJob(j.job_id) } catch (e) { ElMessage.error(errText(e)) } }
async function cancel(j) {
  try { await ElMessageBox.confirm(t('buttons.cancel') + '?', t('main_ui.error_title'), { type: 'warning' }) } catch { return }
  try { await cancelJob(j.job_id) } catch (e) { ElMessage.error(errText(e)) }
}
async function remove(j) {
  try { await removeJob(j.job_id) } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(() => store.fetchJobs())
</script>

<style scoped>
.toolbar-card { display: flex; align-items: center; gap: 12px; }
.toolbar-card .count { margin-left: auto; color: var(--yts-text-dim); }
.job-card { padding: 14px; }
.job-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.fname { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { font-size: 12px; color: var(--yts-text-dim); margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta.dim { display: flex; gap: 16px; }
.job-ops { margin-top: 10px; display: flex; gap: 8px; }
</style>
