<template>
  <div class="sched-page">
    <div class="yts-card">
      <div class="head">
        <h3>{{ t('web.sync.schedule') }}</h3>
        <el-button type="primary" size="small" @click="openForm(null)"><el-icon><Plus /></el-icon> {{ t('web.sync.new_schedule') }}</el-button>
      </div>
      <el-table :data="rows" size="small" stripe v-loading="loading">
        <el-table-column :label="t('web.sync.col_profile')" width="130">
          <template #default="{ row }">{{ profileName(row.profile_id) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.sched_rule')" min-width="180">
          <template #default="{ row }">{{ ruleText(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_last_run')" width="160" align="center">
          <template #default="{ row }">{{ fmtTime(row.last_run) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_next_run')" width="160" align="center">
          <template #default="{ row }">{{ fmtTime(row.next_run) }}</template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_enabled')" width="90" align="center">
          <template #default="{ row }">
            <el-switch size="small" :model-value="!!row.enabled" @change="(v) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column :label="t('web.sync.col_ops')" width="120" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">{{ t('web.sync.edit') }}</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">{{ t('web.sync.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !rows.length" :description="t('web.sync.no_schedules')" :image-size="60" />
    </div>

    <el-dialog v-model="dlg.visible" :title="dlg.id ? t('web.sync.edit_schedule') : t('web.sync.new_schedule')" width="460px">
      <el-form :model="dlg.form" label-width="130px" size="default">
        <el-form-item :label="t('web.sync.col_profile')" required>
          <el-select v-model="dlg.form.profile_id" style="width: 100%">
            <el-option v-for="p in profiles" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('web.sync.sched_mode')">
          <el-radio-group v-model="dlg.form.mode">
            <el-radio value="interval">{{ t('web.sync.sched_interval') }}</el-radio>
            <el-radio value="daily">{{ t('web.sync.sched_daily') }}</el-radio>
            <el-radio value="weekly">{{ t('web.sync.sched_weekly') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="dlg.form.mode === 'interval'" :label="t('web.sync.sched_every')">
          <el-input-number v-model="dlg.form.interval_min" :min="10" :max="10080" /> {{ t('web.sync.minutes') }}
        </el-form-item>
        <template v-else>
          <el-form-item :label="t('web.sync.sched_time')">
            <el-time-select v-model="timeVal" start="00:00" step="00:10" end="23:50" style="width: 120px" />
          </el-form-item>
          <el-form-item v-if="dlg.form.mode === 'weekly'" :label="t('web.sync.sched_weekday')">
            <el-select v-model="dlg.form.weekday" style="width: 140px">
              <el-option v-for="(n, i) in 7" :key="n" :label="weekdayLabel(n)" :value="n" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item :label="t('web.sync.enabled')"><el-switch v-model="dlg.form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.visible = false">{{ t('web.sync.cancel') }}</el-button>
        <el-button type="primary" :loading="dlg.saving" @click="save">{{ t('web.sync.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  listSchedules, createSchedule, updateSchedule, deleteSchedule, listProfiles,
} from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const rows = ref([])
const profiles = ref([])
const loading = ref(false)
const timeVal = ref('00:00')
const dlg = reactive({ visible: false, id: null, form: {}, saving: false })

function profileName(id) {
  const p = profiles.value.find((x) => x.id === id)
  return p ? p.name : `#${id}`
}

function weekdayLabel(n) {
  return ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][(n - 1 + 7) % 7]
}

function ruleText(s) {
  if (s.mode === 'interval') return `${t('web.sync.sched_every')} ${s.interval_min} ${t('web.sync.minutes')}`
  const hh = String(s.hour).padStart(2, '0')
  const mm = String(s.minute).padStart(2, '0')
  if (s.mode === 'daily') return `${t('web.sync.sched_daily')} ${hh}:${mm}`
  return `${t('web.sync.sched_weekly')} (${weekdayLabel(s.weekday)}) ${hh}:${mm}`
}

function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '-' }

async function load() {
  loading.value = true
  try {
    const [a, b] = await Promise.all([listSchedules(), listProfiles()])
    rows.value = a.schedules || []
    profiles.value = b.profiles || []
  } catch (e) { ElMessage.error(errText(e)) } finally { loading.value = false }
}

function openForm(s) {
  if (s) {
    dlg.id = s.id
    dlg.form = { ...s }
    timeVal.value = `${String(s.hour).padStart(2, '0')}:${String(s.minute).padStart(2, '0')}`
  } else {
    dlg.id = null
    dlg.form = { profile_id: profiles.value[0]?.id, mode: 'interval', interval_min: 60, hour: 0, minute: 0, weekday: 1, enabled: true }
    timeVal.value = '00:00'
  }
  dlg.visible = true
}

async function save() {
  dlg.saving = true
  try {
    const [h, m] = timeVal.value.split(':').map(Number)
    dlg.form.hour = h
    dlg.form.minute = m
    if (dlg.id) await updateSchedule(dlg.id, dlg.form)
    else await createSchedule(dlg.form)
    dlg.visible = false
    ElMessage.success(t('web.sync.saved'))
    load()
  } catch (e) { ElMessage.error(errText(e)) } finally { dlg.saving = false }
}

async function toggle(row, v) {
  try { await updateSchedule(row.id, { enabled: v }) } catch (e) { ElMessage.error(errText(e)) }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(t('web.sync.delete_schedule_confirm'), t('web.sync.delete'), { type: 'warning' })
  } catch { return }
  try { await deleteSchedule(row.id); load() } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.head h3 { margin: 0; }
</style>