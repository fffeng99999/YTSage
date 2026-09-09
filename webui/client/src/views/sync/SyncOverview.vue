<template>
  <div class="sync-page">
    <!-- Status cards -->
    <div class="stat-row">
      <div class="stat yts-card">
        <div class="stat-num">{{ st.profiles ?? '-' }}</div>
        <div class="stat-label">{{ t('web.sync.stat_profiles') }}</div>
      </div>
      <div class="stat yts-card">
        <div class="stat-num">{{ st.record_count ?? '-' }}</div>
        <div class="stat-label">{{ t('web.sync.stat_records') }}</div>
      </div>
      <div class="stat yts-card">
        <div class="stat-num" :class="st.running ? 'warn' : ''">{{ st.running ? t('web.sync.running') : t('web.sync.idle') }}</div>
        <div class="stat-label">{{ t('web.sync.stat_sync_state') }}</div>
      </div>
      <div class="stat yts-card">
        <div class="stat-num" :class="needsCookie ? 'warn' : ''">{{ needsCookie }}</div>
        <div class="stat-label">{{ t('web.sync.stat_needs_cookie') }}</div>
      </div>
    </div>

    <el-alert
      v-if="needsCookie"
      type="warning"
      :closable="false"
      :title="t('web.sync.cookie_warning')"
      class="warn-alert"
    />

    <!-- Actions -->
    <div class="yts-card">
      <div class="row">
        <el-button type="primary" size="small" :loading="running" @click="goSources">{{ t('web.sync.configure') }}</el-button>
        <el-button type="success" size="small" :loading="running" @click="syncAll">{{ t('web.sync.sync_all') }}</el-button>
        <el-button size="small" :loading="loading" @click="load"><el-icon><Refresh /></el-icon> {{ t('web.sync.refresh') }}</el-button>
      </div>
    </div>

    <!-- Recent runs -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.recent_runs') }}</div>
      <el-table :data="runs" size="small" stripe>
        <el-table-column :label="t('web.sync.col_time')" width="170">
          <template #default="{ row }">{{ fmtTime(row.run_at) }}</template>
        </el-table-column>
        <el-table-column prop="profile_id" :label="t('web.sync.col_profile')" width="90" />
        <el-table-column :label="t('web.sync.col_summary')" show-overflow-tooltip prop="summary" />
        <el-table-column :label="t('web.sync.col_new')" width="80" align="center">
          <template #default="{ row }"><el-tag size="small" type="success">{{ row.new_count }}</el-tag></template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_skip')" width="80" align="center" prop="skipped" />
        <el-table-column :label="t('web.sync.col_failed')" width="80" align="center">
          <template #default="{ row }"><el-tag size="small" :type="row.failed ? 'danger' : 'info'">{{ row.failed }}</el-tag></template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!runs.length" :description="t('web.sync.no_runs')" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { syncStatus, latestRuns, runSync, listProfiles } from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const router = useRouter()
const st = ref({})
const runs = ref([])
const loading = ref(false)
const running = ref(false)
const profiles = ref([])

const needsCookie = computed(() => st.value.needs_cookie_targets || 0)

async function load() {
  loading.value = true
  try {
    const [a, b, c] = await Promise.all([syncStatus(), latestRuns(), listProfiles()])
    st.value = a
    runs.value = b.runs || []
    profiles.value = c.profiles || []
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loading.value = false
  }
}

async function syncAll() {
  if (running.value) return
  if (!profiles.value.length) { ElMessage.warning(t('web.sync.no_profiles')); goSources(); return }
  running.value = true
  try {
    for (const p of profiles.value) {
      if (!p.enabled) continue
      await runSync(p.id)
    }
    ElMessage.success(t('web.sync.sync_all_done'))
    load()
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    running.value = false
  }
}

function goSources() { router.push('/sync/sources') }
function fmtTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

onMounted(load)
</script>

<style scoped>
.sync-page { display: flex; flex-direction: column; gap: 14px; }
.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.stat { padding: 16px; text-align: center; }
.stat-num { font-size: 26px; font-weight: 700; color: var(--yts-primary, #ff6b6b); }
.stat-num.warn { color: #e6a23c; }
.stat-label { margin-top: 6px; color: var(--yts-text-dim); font-size: 12px; }
.warn-alert { margin-top: 4px; }
.row { display: flex; gap: 10px; }
</style>