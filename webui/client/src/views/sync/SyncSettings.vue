<template>
  <div class="sync-settings-page">
    <!-- General -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.sync_settings') }}</div>
      <el-form label-width="240px" size="default">
        <el-form-item :label="t('web.sync.set_log_retention')">
          <el-input-number v-model="form.log_retention_days" :min="1" :max="365" /> {{ t('web.sync.days') }}
        </el-form-item>
        <el-form-item :label="t('web.sync.set_only_recent_default')">
          <el-switch v-model="form.only_recent_default" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_recent_limit')">
          <el-input-number v-model="form.recent_limit_default" :min="1" :max="200" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_max_per_run')">
          <el-input-number v-model="form.max_sync_per_run" :min="1" :max="500" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_resolution')">
          <el-select v-model="form.resolution" style="width: 140px">
            <el-option v-for="r in ['2160','1440','1080','720','480','360']" :key="r" :label="r + 'p'" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('web.sync.set_auto_distinct')">
          <el-switch v-model="form.auto_distinct" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_auto_clean_logs')">
          <el-switch v-model="form.auto_clean_logs" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">{{ t('web.sync.save') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Download options -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.sync_settings') }} · {{ t('buttons.download') }}</div>
      <el-form label-width="240px" size="default">
        <el-form-item :label="t('web.sync.set_save_thumbnail')">
          <el-switch v-model="form.save_thumbnail" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_save_description')">
          <el-switch v-model="form.save_description" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_naming_template')">
          <el-input v-model="form.video_naming_template" style="width: 360px" />
        </el-form-item>
        <el-form-item>
          <span class="help">{{ t('web.sync.naming_hint') }}</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- Emby / NFO + share -->
    <div class="yts-card">
      <div class="yts-card-title">Emby / Jellyfin</div>
      <el-form label-width="240px" size="default">
        <el-form-item :label="t('web.sync.nfo_enabled')">
          <el-switch v-model="form.nfo_enabled" />
        </el-form-item>
        <el-form-item :label="t('web.sync.share_link')">
          <el-switch v-model="form.share_link_enabled" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">{{ t('web.sync.save') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Log maintenance -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.log_maint') }}</div>
      <div class="row">
        <el-button size="small" @click="clearLogs">{{ t('web.sync.clear_logs') }}</el-button>
        <el-button size="small" @click="pruneLogs">{{ t('web.sync.prune_logs') }}</el-button>
      </div>
    </div>

    <!-- Export / import -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.config_io') }}</div>
      <div class="row">
        <el-button type="success" size="small" :loading="exporting" @click="doExport">{{ t('web.sync.export_conf') }}</el-button>
        <el-upload
          :show-file-list="false"
          accept=".json,application/json"
          :before-upload="doImport"
        >
          <el-button size="small">{{ t('web.sync.import_conf') }}</el-button>
        </el-upload>
      </div>
      <p class="help">{{ t('web.sync.config_io_hint') }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSyncSettings, setSyncSettings, clearSyncLogs, pruneSyncLogs, exportSync, importSync } from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const form = ref({})
const saving = ref(false)
const exporting = ref(false)

async function load() {
  try { form.value = await getSyncSettings() } catch (e) { ElMessage.error(errText(e)) }
}

async function save() {
  saving.value = true
  try { await setSyncSettings(form.value); ElMessage.success(t('web.sync.saved')) } catch (e) { ElMessage.error(errText(e)) } finally { saving.value = false }
}

async function clearLogs() { try { await clearSyncLogs(); ElMessage.success(t('web.sync.logs_cleared')) } catch (e) { ElMessage.error(errText(e)) } }
async function pruneLogs() { try { await pruneSyncLogs(); ElMessage.success(t('web.sync.logs_pruned')) } catch (e) { ElMessage.error(errText(e)) } }

async function doExport() {
  exporting.value = true
  try {
    const data = await exportSync()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `ytsage-sync-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) { ElMessage.error(errText(e)) } finally { exporting.value = false }
}

async function doImport(file) {
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const r = await importSync(data)
    ElMessage.success(t('web.sync.imported', { p: r.profiles, t: r.targets }))
  } catch (e) {
    ElMessage.error(t('web.sync.import_failed') + ': ' + (e.message || e))
  }
  return false
}

onMounted(load)
</script>

<style scoped>
.sync-settings-page { display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; gap: 10px; }
.help { color: var(--yts-text-dim); font-size: 12px; }
</style>