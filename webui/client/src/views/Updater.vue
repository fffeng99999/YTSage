<template>
  <div class="updater-page">
    <!-- ============ yt-dlp ============ -->
    <div class="yts-card">
      <div class="yts-card-title">yt-dlp</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item :label="t('ffmpeg_updater.current_version')">{{ yt.current || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('ffmpeg_updater.latest_version')">{{ yt.latest || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-progress v-if="yt.busy" :percentage="yt.progress || 0" style="margin-top: 10px" />
      <div v-if="yt.log" class="console-output" style="height: 120px; margin-top: 10px">{{ yt.log }}</div>
      <p class="status" :class="statusClass(yt)">{{ ytStatusText }}</p>
      <div class="row">
        <el-button size="small" @click="checkYt" :loading="yt.checking">{{ t('ffmpeg_updater.check_updates') }}</el-button>
        <el-button size="small" type="primary" :disabled="!yt.update_available || yt.busy" @click="updateYt">{{ t('buttons.update') }}</el-button>
        <el-button
          v-if="yt.history && yt.history.rollback_available"
          size="small" type="warning" plain :disabled="yt.busy"
          :title="t('web.rollback.hint')"
          @click="doRollback('ytdlp', yt)"
        >{{ t('web.rollback.to', { version: yt.history.rollback_to }) }}</el-button>
      </div>

      <el-divider />
      <!-- channel -->
      <div class="sub-title">{{ t('settings.ytdlp_channel') }}</div>
      <p class="help">{{ t('settings.ytdlp_channel_description') }}</p>
      <el-radio-group v-model="channel" :disabled="yt.busy" @change="switchChannel">
        <el-radio value="stable">{{ t('settings.ytdlp_channel_stable') }}</el-radio>
        <el-radio value="nightly">{{ t('settings.ytdlp_channel_nightly') }}</el-radio>
      </el-radio-group>
      <p v-if="channelMsg" class="status" :class="channelOk ? 'ok' : 'err'">{{ channelMsg }}</p>

      <el-divider />
      <!-- auto update -->
      <div class="sub-title">{{ t('settings.auto_update_title') }}</div>
      <el-checkbox v-model="auto.enabled">{{ t('settings.enable_auto_updates') }}</el-checkbox>
      <el-radio-group v-model="auto.frequency" style="margin-left: 16px">
        <el-radio value="startup">{{ t('settings.check_startup') }}</el-radio>
        <el-radio value="daily">{{ t('settings.check_daily') }}</el-radio>
        <el-radio value="weekly">{{ t('settings.check_weekly') }}</el-radio>
      </el-radio-group>
      <el-button size="small" style="margin-left: 16px" @click="saveAuto">{{ t('buttons.ok') }}</el-button>
      <p class="help">{{ t('auto_update.last_check', { time: fmtTime(auto.last_check) }) }}</p>
    </div>

    <!-- ============ FFmpeg ============ -->
    <div class="yts-card">
      <div class="yts-card-title">FFmpeg</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item :label="t('ffmpeg_updater.current_version')">{{ ff.current || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('ffmpeg_updater.latest_version')">{{ ff.latest || '-' }}</el-descriptions-item>
      </el-descriptions>
      <p class="status" :class="statusClass(ff)">{{ compStatusText(ff, 'ffmpeg_updater') }}</p>
      <div v-if="ff.busy" class="console-output" style="height: 120px; margin-top: 10px">{{ ff.log }}</div>
      <div class="row">
        <el-button size="small" @click="checkFf" :loading="ff.checking">{{ t('ffmpeg_updater.check_updates') }}</el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="(ff.installed && !ff.update_available) || ff.busy"
          @click="installFf"
        >{{ ff.installed ? t('web.ffmpeg.update_button') : t('ffmpeg.install_button') }}</el-button>
        <a href="https://github.com/yt-dlp/yt-dlp/wiki/FFmpeg-Guide" target="_blank" class="doc-link">{{ t('ffmpeg.manual_guide') }}</a>
      </div>
    </div>

    <!-- ============ Deno ============ -->
    <div class="yts-card">
      <div class="yts-card-title">Deno</div>
      <p class="help">{{ t('deno_updater.description') }}</p>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item :label="t('deno_updater.current_version')">{{ dn.current || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('deno_updater.latest_version')">{{ dn.latest || '-' }}</el-descriptions-item>
      </el-descriptions>
      <p class="status" :class="statusClass(dn)">{{ compStatusText(dn, 'deno_updater') }}</p>
      <div v-if="dn.busy" class="console-output" style="height: 120px; margin-top: 10px">{{ dn.log }}</div>
      <div class="row">
        <el-button size="small" @click="checkDn" :loading="dn.checking">{{ t('deno_updater.check_updates') }}</el-button>
        <el-button size="small" type="primary" :disabled="!dn.update_available || dn.busy" @click="updateDn">{{ t('deno_updater.update_now') }}</el-button>
        <el-button
          v-if="dn.history && dn.history.rollback_available"
          size="small" type="warning" plain :disabled="dn.busy"
          :title="t('web.rollback.hint')"
          @click="doRollback('deno', dn)"
        >{{ t('web.rollback.to', { version: dn.history.rollback_to }) }}</el-button>
      </div>
    </div>

    <!-- ============ App ============ -->
    <div class="yts-card">
      <div class="yts-card-title">{{ t('update.title') }} — YTSage</div>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item :label="t('update_dialog.current_version_label')">{{ app.current || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('update_dialog.latest_version_label')">{{ app.latest || '-' }}</el-descriptions-item>
      </el-descriptions>
      <p v-if="app.update_available" class="status warn">{{ t('update_dialog.new_version_available') }}</p>
      <p v-else-if="app.latest" class="status ok">{{ t('update.already_latest') }}</p>
      <div v-if="app.changelog" class="changelog" v-html="app.changelogHtml"></div>
      <div class="row">
        <el-button size="small" @click="doCheckApp" :loading="app.checking">{{ t('auto_update.check_now') }}</el-button>
        <el-button v-if="app.update_available && app.release_url" size="small" type="primary" tag="a" :href="app.release_url" target="_blank">
          {{ t('update_dialog.download_update') }}
        </el-button>
      </div>
      <el-divider />
      <el-checkbox v-model="appCfg.check_app_updates" @change="saveAppCfg">{{ t('settings.check_app_updates') }}</el-checkbox>
      <el-checkbox v-model="appCfg.check_beta_updates" @change="saveAppCfg" style="margin-left: 16px">{{ t('settings.check_beta_updates') }}</el-checkbox>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  updaterState, checkYtdlp, updateYtdlp, rollbackYtdlp, setYtdlpChannel, setYtdlpAuto,
  checkFfmpeg, installFfmpeg, rollbackFfmpeg, checkDeno, updateDeno, rollbackDeno, checkApp,
} from '@/api/updater'
import { useSettingsStore } from '@/stores/settings'
import { useDownloadStore } from '@/stores/download'
import { errText } from '@/api/http'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const downloadStore = useDownloadStore()

const yt = ref({ current: '', latest: '', update_available: false, checking: false, busy: false, progress: 0 })
const ff = ref({ installed: false, current: '', latest: '', update_available: false, checking: false, busy: false, log: '' })
const dn = ref({ installed: false, current: '', latest: '', update_available: false, checking: false, busy: false, log: '' })
const app = ref({ current: '', latest: '', update_available: false, checking: false, changelog: '', release_url: '' })
const channel = ref('stable')
const channelMsg = ref('')
const channelOk = ref(true)
const auto = ref({ enabled: true, frequency: 'daily', last_check: 0 })
const appCfg = ref({ check_app_updates: true, check_beta_updates: false })

const ytStatusText = computed(() => {
  if (yt.value.busy) return t('update.updating')
  if (!yt.value.latest) return ''
  return yt.value.update_available ? t('update.update_available') : t('update.already_up_to_date')
})

function statusClass(c) {
  if (c.busy) return 'warn'
  if (c.error) return 'err'
  if (c.update_available) return 'warn'
  if (c.installed === false) return 'err'
  return 'ok'
}
function compStatusText(c, ns) {
  if (c.checking) return t(`${ns}.status_checking`)
  if (c.busy) return t(`${ns}.updating`)
  if (c.installed === false) return t(`${ns}.status_not_installed`)
  if (c.update_available) return t(`${ns}.status_update_available`)
  if (c.latest) return t(`${ns}.status_up_to_date`)
  return t(`${ns}.status_idle`)
}
function fmtTime(ts) {
  if (!ts) return t('auto_update.last_check_never')
  return new Date(ts * 1000).toLocaleString()
}

// Route WS updater events into component state
watch(() => downloadStore.updaterEvents, (ev) => {
  if (ev.ytdlp) {
    const e = ev.ytdlp
    if (e.state === 'updating') { yt.value.busy = true; yt.value.progress = e.progress || 0 }
    else if (e.state === 'done') { yt.value.busy = false; yt.value.progress = 100; checkYt() }
    else if (e.state === 'failed') { yt.value.busy = false; ElMessage.error(t('update.update_failed')) }
    else if (e.state === 'switching_channel') { yt.value.busy = true }
    else if (e.state === 'channel_switched') { yt.value.busy = false }
    else if (e.state === 'rolling_back') { yt.value.busy = true; if (e.message) yt.value.log += e.message + '\n' }
    else if (e.state === 'rolled_back') { yt.value.busy = false; checkYt() }
  }
  if (ev.ffmpeg) {
    const e = ev.ffmpeg
    if (e.state === 'installing') { ff.value.busy = true; if (e.message) ff.value.log += e.message + '\n' }
    else if (e.state === 'done') { ff.value.busy = false; ElMessage.success(e.updated ? t('web.ffmpeg.update_success') : t('ffmpeg.install_success')); checkFf() }
    else if (e.state === 'failed') { ff.value.busy = false; ElMessage.error(t('ffmpeg.installation_failed')) }
    else if (e.state === 'rolling_back') { ff.value.busy = true; if (e.message) ff.value.log += e.message + '\n' }
    else if (e.state === 'rolled_back') { ff.value.busy = false; checkFf() }
  }
  if (ev.deno) {
    const e = ev.deno
    if (e.state === 'upgrading') { dn.value.busy = true; if (e.message) dn.value.log += e.message + '\n' }
    else if (e.state === 'done') { dn.value.busy = false; ElMessage.success(t('deno_updater.update_success')); checkDn() }
    else if (e.state === 'failed') { dn.value.busy = false; ElMessage.error(t('deno_updater.update_failed')) }
    else if (e.state === 'rolling_back') { dn.value.busy = true; if (e.message) dn.value.log += e.message + '\n' }
    else if (e.state === 'rolled_back') { dn.value.busy = false; checkDn() }
  }
}, { deep: true })

async function checkYt() {
  yt.value.checking = true
  try { Object.assign(yt.value, await checkYtdlp()) } catch (e) { ElMessage.error(errText(e)) }
  finally { yt.value.checking = false }
}
async function updateYt() {
  yt.value.busy = true
  try { const r = await updateYtdlp(); if (!r.success) ElMessage.error(t('update.update_failed')) }
  catch (e) { ElMessage.error(errText(e)) }
  finally { yt.value.busy = false; checkYt() }
}
async function switchChannel(v) {
  channelMsg.value = t('settings.ytdlp_switching_channel', { channel: v })
  yt.value.busy = true
  try {
    await setYtdlpChannel(v)
    channelOk.value = true
    channelMsg.value = t('settings.ytdlp_channel_switched', { channel: v })
  } catch (e) {
    channelOk.value = false
    channelMsg.value = t('settings.ytdlp_channel_switch_failed', { error: errText(e) })
    channel.value = v === 'stable' ? 'nightly' : 'stable'
  } finally { yt.value.busy = false }
}
async function saveAuto() {
  try { await setYtdlpAuto(auto.value.enabled, auto.value.frequency); ElMessage.success(t('settings.settings_saved_successfully')) }
  catch (e) { ElMessage.error(errText(e)) }
}
async function checkFf() {
  ff.value.checking = true
  try { Object.assign(ff.value, await checkFfmpeg()) } catch (e) { ElMessage.error(errText(e)) }
  finally { ff.value.checking = false }
}
async function installFf() {
  ff.value.busy = true; ff.value.log = ''
  try {
    const r = await installFfmpeg()
    if (!r.success) ElMessage.error(t('ffmpeg.installation_failed'))
    else if (r.noop) ElMessage.info(t('ffmpeg_updater.status_up_to_date'))
    else ElMessage.success(r.updated ? t('web.ffmpeg.update_success') : t('ffmpeg.install_success'))
  }
  catch (e) { ElMessage.error(errText(e)) }
  finally { ff.value.busy = false; checkFf() }
}
async function checkDn() {
  dn.value.checking = true
  try { Object.assign(dn.value, await checkDeno()) } catch (e) { ElMessage.error(errText(e)) }
  finally { dn.value.checking = false }
}
async function updateDn() {
  dn.value.busy = true; dn.value.log = ''
  try { const r = await updateDeno(); if (!r.success) ElMessage.error(t('deno_updater.update_failed')) }
  catch (e) { ElMessage.error(errText(e)) }
  finally { dn.value.busy = false; checkDn() }
}

const rollbackFns = { ytdlp: rollbackYtdlp, ffmpeg: rollbackFfmpeg, deno: rollbackDeno }
const rollbackChecks = { ytdlp: checkYt, ffmpeg: checkFf, deno: checkDn }
async function doRollback(comp, card) {
  const target = card.history?.rollback_to
  if (!target) { ElMessage.info(t('web.rollback.no_history')); return }
  try {
    await ElMessageBox.confirm(
      t('web.rollback.confirm_message', { version: target }),
      t('web.rollback.confirm_title'),
      { type: 'warning', confirmButtonText: t('web.rollback.button'), cancelButtonText: t('buttons.cancel') },
    )
  } catch { return }
  card.log = ''
  card.busy = true
  try {
    const r = await rollbackFns[comp]()
    if (r.success) ElMessage.success(t('web.rollback.success', { version: r.version || target }))
    else ElMessage.error(t('web.rollback.failed', { error: r.error || 'unknown' }))
  } catch (e) {
    ElMessage.error(t('web.rollback.failed', { error: errText(e) }))
  } finally {
    card.busy = false
    rollbackChecks[comp]()
  }
}
async function doCheckApp() {
  app.value.checking = true
  try {
    const r = await checkApp()
    r.changelogHtml = simpleMarkdown(r.changelog || '')
    Object.assign(app.value, r)
  } catch (e) { ElMessage.error(errText(e)) }
  finally { app.value.checking = false }
}
async function saveAppCfg() {
  try { await settingsStore.save({ check_app_updates: appCfg.value.check_app_updates, check_beta_updates: appCfg.value.check_beta_updates }) }
  catch (e) { ElMessage.error(errText(e)) }
}

function simpleMarkdown(md) {
  if (!md) return ''
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.*)$/gm, '<h4>$1</h4>')
    .replace(/^## (.*)$/gm, '<h3>$1</h3>')
    .replace(/^# (.*)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.*)$/gm, '• $1')
    .replace(/\n/g, '<br>')
}

onMounted(async () => {
  try {
    const s = await updaterState()
    Object.assign(yt.value, s.ytdlp)
    channel.value = s.ytdlp.channel
    Object.assign(ff.value, s.ffmpeg)
    Object.assign(dn.value, s.deno)
    Object.assign(auto.value, s.auto_update)
    Object.assign(appCfg.value, s.app_updates)
  } catch (e) { ElMessage.error(errText(e)) }
})
</script>

<style scoped>
.sub-title { font-weight: 600; margin-bottom: 6px; }
.help { color: var(--yts-text-dim); font-size: 12px; }
.status { font-size: 13px; margin: 8px 0; }
.status.ok { color: #00e676; }
.status.warn { color: #ffaa00; }
.status.err { color: #ff6666; }
.row { display: flex; gap: 10px; align-items: center; }
.doc-link { color: var(--yts-red); font-size: 13px; }
.changelog { max-height: 200px; overflow-y: auto; font-size: 13px; color: var(--yts-text-dim); margin: 10px 0; border: 1px solid var(--yts-border); border-radius: 6px; padding: 10px; }
:deep(.el-divider__text) { background: var(--yts-panel); }
</style>
