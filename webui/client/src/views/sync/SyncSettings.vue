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
        <el-form-item :label="t('web.sync.set_retry_failed')">
          <el-switch v-model="form.retry_failed" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">{{ t('web.sync.save') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Anti-bot / throttling (dysync parity) -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.anti_bot_section') }}</div>
      <el-form label-width="240px" size="default">
        <el-form-item :label="t('web.sync.set_anti_bot')">
          <el-switch v-model="form.anti_bot_enabled" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_sleep_min')">
          <el-input-number v-model="form.sleep_min" :min="0" :max="60" :disabled="!form.anti_bot_enabled" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_sleep_max')">
          <el-input-number v-model="form.sleep_max" :min="0" :max="120" :disabled="!form.anti_bot_enabled" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_ua_disguise')">
          <el-switch v-model="form.ua_disguise" :disabled="!form.anti_bot_enabled" />
        </el-form-item>
        <el-form-item :label="t('web.sync.set_user_agent')">
          <el-input v-model="form.user_agent" style="width: 360px" :disabled="!form.anti_bot_enabled" placeholder="Mozilla/5.0 ..." />
        </el-form-item>
        <el-form-item>
          <span class="help">{{ t('web.sync.anti_bot_hint') }}</span>
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
        <el-form-item :label="t('web.sync.set_episode_naming')">
          <el-switch v-model="form.episode_naming" />
        </el-form-item>
        <el-form-item :label="t('web.sync.share_link')">
          <el-switch v-model="form.share_link_enabled" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">{{ t('web.sync.save') }}</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Database backend (dysync: 数据库配置 + 迁移) -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('web.sync.db_section') }}</div>
      <el-form label-width="240px" size="default">
        <el-form-item :label="t('web.sync.db_type')">
          <el-select v-model="dbForm.type" style="width: 200px" @change="onDbTypeChange">
            <el-option label="SQLite (default)" value="sqlite" />
            <el-option label="MySQL" value="mysql" />
            <el-option label="PostgreSQL" value="postgresql" />
          </el-select>
        </el-form-item>

        <template v-if="dbForm.type === 'sqlite'">
          <el-form-item :label="t('web.sync.db_sqlite_path')">
            <el-input v-model="dbForm.sqlite_path" style="width: 360px" placeholder="(default)" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item :label="t('web.sync.db_host')">
            <el-input v-model="dbForm.host" style="width: 240px" />
          </el-form-item>
          <el-form-item :label="t('web.sync.db_port')">
            <el-input-number v-model="dbForm.port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item :label="t('web.sync.db_name')">
            <el-input v-model="dbForm.database" style="width: 240px" />
          </el-form-item>
          <el-form-item :label="t('web.sync.db_user')">
            <el-input v-model="dbForm.user" style="width: 240px" />
          </el-form-item>
          <el-form-item :label="t('web.sync.db_password')">
            <el-input v-model="dbForm.password" type="password" show-password style="width: 240px" placeholder="(unchanged)" />
          </el-form-item>
          <el-form-item :label="t('web.sync.db_ssl')">
            <el-switch v-model="dbForm.ssl" />
          </el-form-item>
        </template>

        <el-form-item>
          <div class="row">
            <el-button size="small" :loading="dbTesting" @click="testDb">{{ t('web.sync.db_test') }}</el-button>
            <el-button size="small" type="primary" :loading="dbBusy" @click="doMigrate">{{ t('web.sync.db_migrate') }}</el-button>
            <el-button size="small" :loading="dbBusy" @click="doSwitch">{{ t('web.sync.db_switch') }}</el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <span class="help">{{ t('web.sync.db_driver_hint') }}</span>
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
import {
  getSyncSettings, setSyncSettings, clearSyncLogs, pruneSyncLogs, exportSync, importSync,
  getDatabaseConfig, testDatabase, migrateDatabase, switchDatabase,
} from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const form = ref({})
const saving = ref(false)
const exporting = ref(false)

// ---- database backend ---------------------------------------------------

const dbForm = ref({ type: 'sqlite', sqlite_path: '', host: '127.0.0.1', port: 3306,
  database: 'ytsage', user: '', password: '', ssl: false })
const dbTesting = ref(false)
const dbBusy = ref(false)
const DEFAULT_PORTS = { mysql: 3306, postgresql: 5432 }

function onDbTypeChange(type) {
  if (type !== 'sqlite' && (!dbForm.value.port || dbForm.value.port === 3306)) {
    dbForm.value.port = DEFAULT_PORTS[type] || 3306
  }
}

function dbPayload() {
  const d = { ...dbForm.value }
  if (d.type === 'sqlite') {
    return { type: 'sqlite', sqlite_path: d.sqlite_path || '' }
  }
  return {
    type: d.type, host: d.host, port: Number(d.port) || DEFAULT_PORTS[d.type] || 3306,
    database: d.database, user: d.user, password: d.password || '', ssl: !!d.ssl,
  }
}

async function loadDb() {
  try {
    const r = await getDatabaseConfig()
    const c = r.config || {}
    dbForm.value = {
      type: c.type || 'sqlite',
      sqlite_path: c.type === 'sqlite' ? (c.sqlite_path || '') : '',
      host: c.host || '127.0.0.1',
      port: c.port || DEFAULT_PORTS[c.type] || 3306,
      database: c.database || 'ytsage',
      user: c.user || '',
      password: '',            // never displayed back
      ssl: !!c.ssl,
    }
  } catch (e) { ElMessage.error(errText(e)) }
}

async function testDb() {
  dbTesting.value = true
  try {
    await testDatabase(dbPayload())
    ElMessage.success(t('web.sync.db_test_ok'))
  } catch (e) {
    ElMessage.error(t('web.sync.db_test_fail') + ': ' + errText(e))
  } finally { dbTesting.value = false }
}

async function doMigrate() {
  try { await ElMessageBox.confirm(t('web.sync.db_migrate_confirm'), t('web.sync.db_section'), { type: 'warning' }) } catch { return }
  dbBusy.value = true
  try {
    const r = await migrateDatabase(dbPayload())
    ElMessage.success(t('web.sync.db_migrate_done', { rows: r.rows || 0, n: Object.keys(r.tables || {}).length }))
    loadDb()
  } catch (e) { ElMessage.error(errText(e)) } finally { dbBusy.value = false }
}

async function doSwitch() {
  try { await ElMessageBox.confirm(t('web.sync.db_switch_confirm'), t('web.sync.db_section'), { type: 'warning' }) } catch { return }
  dbBusy.value = true
  try {
    await switchDatabase(dbPayload())
    ElMessage.success(t('web.sync.saved'))
    loadDb()
  } catch (e) { ElMessage.error(errText(e)) } finally { dbBusy.value = false }
}

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

onMounted(() => { load(); loadDb() })
</script>

<style scoped>
.sync-settings-page { display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; gap: 10px; }
.help { color: var(--yts-text-dim); font-size: 12px; }
</style>