<template>
  <div class="cookies-page">
    <div class="yts-card">
      <div class="head">
        <h3>{{ t('web.sync.cookie_status') }}</h3>
        <div class="row">
          <el-button size="small" :loading="checkingAll" @click="checkAll">{{ t('web.sync.cookie_check_all') }}</el-button>
          <el-button size="small" :icon="Refresh" @click="load">{{ t('web.sync.refresh') }}</el-button>
        </div>
      </div>
      <p class="help">{{ t('web.sync.cookie_need_check') }}</p>

      <el-empty v-if="!rows.length" :description="t('web.sync.no_profiles')" :image-size="70" />
      <div v-for="c in rows" :key="c.profile_id" class="cookie-card">
        <div class="cc-head">
          <span class="cc-name">{{ c.profile_name }}</span>
          <el-tag size="small" :type="sourceType(c.cookie_source)">{{ sourceLabel(c.cookie_source) }}</el-tag>
          <el-tag size="small" :type="validType(c.cookie_valid)">{{ validLabel(c.cookie_valid) }}</el-tag>
        </div>
        <div class="cc-meta">
          <span v-if="c.cookie_source === 'browser'">{{ t('web.sync.cookie_browser') }}: {{ c.cookie_browser || 'chrome' }}</span>
          <span v-else-if="c.cookie_source === 'file'"><code>{{ c.cookie_file_path || '-' }}</code><el-tag v-if="!c.has_cookie" size="small" type="danger" style="margin-left:6px">{{ t('web.sync.cookie_expired') }}</el-tag></span>
          <span v-else-if="c.cookie_source === 'global'">{{ t('web.sync.cookie_source_global') }}</span>
          <span v-else>{{ t('web.sync.cookie_unknown') }}</span>
          <span class="dim">{{ t('web.sync.cookie_last_check') }}: {{ c.checked_at ? fmtTime(c.checked_at) : t('web.sync.cookie_never_checked') }}</span>
        </div>
        <el-alert v-if="c.check_error" type="error" :closable="false" :title="c.check_error" class="cc-err" />
        <div class="cc-actions">
          <el-button size="small" type="primary" :loading="checking === c.profile_id" @click="check(c.profile_id)">{{ t('web.sync.cookie_check') }}</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getCookieStatus, checkCookie } from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const rows = ref([])
const checking = ref(null)
const checkingAll = ref(false)

function sourceLabel(s) {
  return { browser: t('web.sync.cookie_browser'), file: t('web.sync.cookie_file'), global: t('web.sync.cookie_global'), none: t('web.sync.cookie_unknown') }[s] || s || '-'
}
function sourceType(s) {
  return { browser: 'primary', file: 'success', global: 'warning' }[s] || 'info'
}
function validLabel(v) {
  if (v === true) return t('web.sync.cookie_valid')
  if (v === false) return t('web.sync.cookie_expired')
  return t('web.sync.cookie_unknown')
}
function validType(v) {
  if (v === true) return 'success'
  if (v === false) return 'danger'
  return 'info'
}
function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '-' }

async function load() {
  try { rows.value = (await getCookieStatus()).cookies || [] }
  catch (e) { ElMessage.error(errText(e)) }
}

async function check(pid) {
  checking.value = pid
  try {
    const r = await checkCookie(pid)
    ElMessage[r.cookie_valid ? 'success' : 'warning'](r.cookie_valid ? t('web.sync.cookie_valid') : (t('web.sync.cookie_expired') + (r.error ? ': ' + r.error : '')))
    await load()
  } catch (e) { ElMessage.error(errText(e)) } finally { checking.value = null }
}

async function checkAll() {
  if (!rows.value.length) return
  checkingAll.value = true
  try {
    for (const c of rows.value) { await checkCookie(c.profile_id) }
    ElMessage.success(t('web.sync.cookie_checked'))
    await load()
  } catch (e) { ElMessage.error(errText(e)) } finally { checkingAll.value = false }
}

onMounted(load)
</script>

<style scoped>
.cookies-page { display: flex; flex-direction: column; gap: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.head h3 { margin: 0; }
.row { display: flex; gap: 8px; }
.help { color: var(--yts-text-dim); font-size: 12px; margin: 0 0 12px; }
.cookie-card { border: 1px solid var(--yts-border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.cc-head { display: flex; align-items: center; gap: 10px; }
.cc-name { font-weight: 600; color: var(--yts-text); }
.cc-meta { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; font-size: 12px; color: var(--yts-text-dim); }
.cc-meta code { font-size: 11px; }
.cc-meta .dim { opacity: 0.8; }
.cc-err { margin-top: 8px; }
.cc-actions { margin-top: 10px; }
</style>
