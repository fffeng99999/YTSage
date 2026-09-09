<template>
  <div class="subs-page">
    <div class="yts-card">
      <div class="head">
        <h3>{{ t('web.sync.subscriptions') }}</h3>
        <div class="row">
          <el-select v-model="profileId" size="small" style="width: 180px" @change="loadSubs">
            <el-option v-for="p in profiles" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button size="small" :loading="pulling" @click="pull">{{ t('web.sync.sub_pull') }}</el-button>
          <el-button size="small" @click="openAdd">{{ t('web.sync.sub_add_manual') }}</el-button>
        </div>
      </div>
      <p class="help">{{ t('web.sync.sub_pull_hint') }}</p>

      <div v-if="pulled.length" class="pull-bar">
        <span>{{ t('web.sync.sub_total') }} {{ pulled.length }} {{ t('web.sync.kind_channel') }}</span>
        <el-select v-model="pullMode" size="small" style="width: 130px">
          <el-option :label="t('web.sync.sub_sync_off')" value="off" />
          <el-option :label="t('web.sync.sub_sync_on')" value="sync" />
          <el-option :label="t('web.sync.sub_sync_full')" value="full_sync" />
        </el-select>
        <el-button size="small" type="primary" :loading="savingSubs" @click="savePulled">{{ t('web.sync.sub_save_all') }}</el-button>
      </div>

      <div class="filter-bar">
        <el-input v-model="kw" size="small" style="width: 220px" clearable :placeholder="t('web.sync.sub_search')" :prefix-icon="Search" />
        <el-radio-group v-model="modeFilter" size="small">
          <el-radio-button value="all">{{ t('web.sync.sub_total') }}</el-radio-button>
          <el-radio-button value="off">{{ t('web.sync.sub_sync_off') }}</el-radio-button>
          <el-radio-button value="sync">{{ t('web.sync.sub_sync_on') }}</el-radio-button>
          <el-radio-button value="full_sync">{{ t('web.sync.sub_sync_full') }}</el-radio-button>
        </el-radio-group>
        <span class="dim">{{ t('web.sync.sub_total') }} {{ filtered.length }}</span>
      </div>

      <el-empty v-if="!filtered.length" :description="t('web.sync.no_targets')" :image-size="60" />
      <div v-for="s in filtered" :key="s.id" class="sub-card">
        <div class="sc-avatar">
          <img v-if="s.avatar_url" :src="thumb(s.avatar_url)" @error="s.avatar_url=''" loading="lazy" />
          <span v-else>{{ (s.title || '?').charAt(0).toUpperCase() }}</span>
        </div>
        <div class="sc-main">
          <div class="sc-name">{{ s.title || s.channel_id || s.url }}</div>
          <div class="sc-meta">
            <span>{{ t('web.sync.sub_last_sync') }}: {{ fmtTime(s.last_sync_at) }}</span>
            <span v-if="s.save_path" class="path"><code>{{ s.save_path }}</code></span>
          </div>
        </div>
        <div class="sc-ops">
          <el-segmented v-model="s._mode" :options="modeOptions" size="small" @change="(v) => setMode(s, v)" />
          <el-button link size="small" @click="editPath(s)">{{ t('web.sync.sub_save_path') }}</el-button>
          <el-button link type="success" size="small" :loading="running === s.id" @click="syncOne(s)">{{ t('web.sync.sub_sync_now') }}</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="addDlg.visible" :title="t('web.sync.sub_add_manual')" width="480px">
      <el-form label-width="110px">
        <el-form-item :label="t('web.sync.sub_channel_url')" required>
          <el-input v-model="addDlg.url" placeholder="https://www.youtube.com/@handle" />
        </el-form-item>
        <el-form-item :label="t('web.sync.sub_channel_name')">
          <el-input v-model="addDlg.name" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg.visible = false">{{ t('web.sync.cancel') }}</el-button>
        <el-button type="primary" :loading="addDlg.saving" @click="doAdd">{{ t('web.sync.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  listProfiles, getSubscriptions, pullSubscriptions, saveSubscriptions,
  addSubscription, updateTargetSyncMode, updateTargetSavePath, runSync,
} from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()
const profiles = ref([])
const profileId = ref(null)
const subs = ref([])
const pulled = ref([])
const pullMode = ref('off')
const pulling = ref(false)
const savingSubs = ref(false)
const running = ref(null)
const kw = ref('')
const modeFilter = ref('all')

const modeOptions = computed(() => [
  { label: t('web.sync.sub_sync_off'), value: 'off' },
  { label: t('web.sync.sub_sync_on'), value: 'sync' },
  { label: t('web.sync.sub_sync_full'), value: 'full_sync' },
])

const filtered = computed(() => {
  let list = subs.value
  if (modeFilter.value !== 'all') list = list.filter((s) => (s.sync_mode || 'sync') === modeFilter.value)
  if (kw.value) {
    const k = kw.value.toLowerCase()
    list = list.filter((s) => (s.title || '').toLowerCase().includes(k) || (s.channel_id || '').toLowerCase().includes(k))
  }
  return list
})

function thumb(url) { return `/api/thumbnail?url=${encodeURIComponent(url)}` }
function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString() : '-' }

async function load() {
  profiles.value = (await listProfiles()).profiles || []
  if (!profileId.value && profiles.value.length) profileId.value = profiles.value[0].id
  await loadSubs()
}

async function loadSubs() {
  if (!profileId.value) { subs.value = []; return }
  try {
    const list = await getSubscriptions(profileId.value)
    subs.value = (Array.isArray(list) ? list : []).map((s) => ({ ...s, _mode: s.sync_mode || 'sync' }))
  } catch (e) { ElMessage.error(errText(e)) }
}

async function pull() {
  if (!profileId.value) return
  pulling.value = true
  try {
    const r = await pullSubscriptions(profileId.value)
    pulled.value = r.subscriptions || []
    if (!pulled.value.length) ElMessage.warning(t('web.sync.sub_needs_cookie'))
    else ElMessage.success(`${t('web.sync.sub_total')} ${pulled.value.length}`)
  } catch (e) { ElMessage.error(errText(e)) } finally { pulling.value = false }
}

async function savePulled() {
  if (!pulled.value.length) return
  savingSubs.value = true
  try {
    const r = await saveSubscriptions(profileId.value, pulled.value, pullMode.value)
    ElMessage.success(r.added ? t('web.sync.sub_saved', { n: r.added }) : t('web.sync.sub_none_pulled'))
    pulled.value = []
    await loadSubs()
  } catch (e) { ElMessage.error(errText(e)) } finally { savingSubs.value = false }
}

async function setMode(s, v) {
  const mode = typeof v === 'object' ? v.value : v
  try { await updateTargetSyncMode(s.id, mode); s.sync_mode = mode; s._mode = mode }
  catch (e) { ElMessage.error(errText(e)); s._mode = s.sync_mode }
}

async function editPath(s) {
  let val = s.save_path || ''
  try {
    const r = await ElMessageBox.prompt(t('web.sync.sub_save_path'), t('web.sync.sub_save_path'), { inputValue: val, inputPlaceholder: 'D:/yt_sync/channelA' })
    val = r.value || ''
  } catch { return }
  try { await updateTargetSavePath(s.id, val); s.save_path = val; ElMessage.success(t('web.sync.saved')) }
  catch (e) { ElMessage.error(errText(e)) }
}

async function syncOne(s) {
  if (!profileId.value) return
  running.value = s.id
  try {
    const r = await runSync(profileId.value, [s.id])
    ElMessage.success(t('web.sync.run_done', { n: r.new }))
    await loadSubs()
  } catch (e) { ElMessage.error(errText(e)) } finally { running.value = null }
}

const addDlg = reactive({ visible: false, url: '', name: '', saving: false })
function openAdd() { addDlg.url = ''; addDlg.name = ''; addDlg.visible = true }
async function doAdd() {
  if (!addDlg.url || !profileId.value) return
  addDlg.saving = true
  try {
    await addSubscription(profileId.value, addDlg.url, addDlg.name || undefined)
    addDlg.visible = false
    ElMessage.success(t('web.sync.saved'))
    await loadSubs()
  } catch (e) { ElMessage.error(errText(e)) } finally { addDlg.saving = false }
}

onMounted(load)
</script>

<style scoped>
.subs-page { display: flex; flex-direction: column; gap: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.head h3 { margin: 0; }
.row { display: flex; gap: 8px; }
.help { color: var(--yts-text-dim); font-size: 12px; margin: 0 0 10px; }
.pull-bar { display: flex; align-items: center; gap: 12px; padding: 10px 12px; background: rgba(201,0,0,0.08); border-radius: 8px; margin-bottom: 12px; font-size: 13px; color: var(--yts-text); }
.filter-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.filter-bar .dim { margin-left: auto; font-size: 12px; color: var(--yts-text-dim); }
.sub-card { display: flex; align-items: center; gap: 12px; border: 1px solid var(--yts-border); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }
.sc-avatar { width: 44px; height: 44px; border-radius: 50%; overflow: hidden; background: rgba(201,0,0,0.25); color: #ff8a8a; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.sc-avatar img { width: 100%; height: 100%; object-fit: cover; }
.sc-main { flex: 1; min-width: 0; }
.sc-name { font-weight: 600; color: var(--yts-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc-meta { display: flex; gap: 16px; font-size: 12px; color: var(--yts-text-dim); margin-top: 3px; }
.sc-meta code { font-size: 11px; }
.sc-ops { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
</style>
