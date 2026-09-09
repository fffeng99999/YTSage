<template>
  <div class="syncs-page">
    <div class="yts-card">
      <div class="head">
        <h3>{{ t('web.sync.sources') }}</h3>
        <el-button type="primary" size="small" @click="openProfile(null)">
          <el-icon><Plus /></el-icon> {{ t('web.sync.new_profile') }}
        </el-button>
      </div>

      <div v-for="p in profiles" :key="p.id" class="profile-card">
        <div class="profile-head">
          <div class="p-title">
            <el-icon :size="16"><FolderOpened /></el-icon>
            <span class="p-name">{{ p.name }}</span>
            <el-tag size="small" :type="p.enabled ? 'success' : 'info'">{{ p.enabled ? t('web.sync.enabled') : t('web.sync.disabled') }}</el-tag>
          </div>
          <div class="p-actions">
            <el-button size="small" type="success" :loading="runningProfile === p.id" @click="runProfile(p)">
              {{ t('web.sync.sync_now') }}
            </el-button>
            <el-button size="small" @click="openTarget(p, null)">{{ t('web.sync.add_target') }}</el-button>
            <el-button size="small" @click="openProfile(p)">{{ t('web.sync.edit') }}</el-button>
            <el-button size="small" type="danger" @click="removeProfile(p)">{{ t('web.sync.delete') }}</el-button>
          </div>
        </div>
        <div class="p-meta">
          <span>{{ t('web.sync.path') }}: <code>{{ p.root_path || '-' }}</code></span>
          <span v-if="p.only_recent">{{ t('web.sync.only_recent_short', { n: p.recent_limit }) }}</span>
        </div>

        <el-table :data="targetsOf(p.id)" size="small" stripe v-if="targetsOf(p.id).length">
          <el-table-column :label="t('web.sync.col_kind')" width="110">
            <template #default="{ row }">
              <el-tag size="small">{{ kindLabel(row.kind) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="title" :label="t('web.sync.col_title')" show-overflow-tooltip />
          <el-table-column :label="t('web.sync.col_url')" show-overflow-tooltip>
            <template #default="{ row }"><span class="url">{{ row.url || '-' }}</span></template>
          </el-table-column>
          <el-table-column :label="t('web.sync.col_folder')" show-overflow-tooltip prop="folder" />
          <el-table-column :label="t('web.sync.col_enabled')" width="90" align="center">
            <template #default="{ row }">
              <el-switch size="small" :model-value="!!row.enabled" @change="(v) => toggleTarget(row, v)" />
            </template>
          </el-table-column>
          <el-table-column :label="t('web.sync.col_ops')" width="130" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openTarget(p, row)">{{ t('web.sync.edit') }}</el-button>
              <el-button link type="danger" size="small" @click="removeTarget(row)">{{ t('web.sync.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :description="t('web.sync.no_targets')" :image-size="50" />
      </div>
      <el-empty v-if="!profiles.length" :description="t('web.sync.no_profiles')" />
    </div>

    <!-- Profile dialog -->
    <el-dialog v-model="profileDlg.visible" :title="profileDlg.id ? t('web.sync.edit_profile') : t('web.sync.new_profile')" width="560px">
      <el-form :model="profileDlg.form" label-width="150px" size="default">
        <el-form-item :label="t('web.sync.name')" required><el-input v-model="profileDlg.form.name" /></el-form-item>
        <el-form-item :label="t('web.sync.root_path')" required>
          <el-input v-model="profileDlg.form.root_path" :placeholder="t('web.sync.root_path_ph')" />
        </el-form-item>
        <el-form-item :label="t('web.sync.cookie_source')">
          <el-radio-group v-model="profileDlg.form.cookie_source">
            <el-radio value="browser">{{ t('web.sync.cookie_browser') }}</el-radio>
            <el-radio value="file">{{ t('web.sync.cookie_file') }}</el-radio>
            <el-radio value="global">{{ t('web.sync.cookie_global') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="profileDlg.form.cookie_source === 'browser'" :label="t('web.sync.cookie_browser')">
          <el-select v-model="profileDlg.form.cookie_browser" style="width: 200px">
            <el-option v-for="b in ['chrome','firefox','edge','brave','opera','vivaldi']" :key="b" :label="b" :value="b" />
          </el-select>
        </el-form-item>
        <el-form-item v-else-if="profileDlg.form.cookie_source === 'file'" :label="t('web.sync.cookie_file')">
          <el-input v-model="profileDlg.form.cookie_file_path" :placeholder="t('web.sync.cookie_file_ph')" />
        </el-form-item>
        <el-form-item v-else :label="t('web.sync.cookie_source')">
          <span class="dim">{{ t('web.sync.cookie_source_global') }}</span>
        </el-form-item>
        <el-form-item :label="t('web.sync.only_recent')"><el-switch v-model="profileDlg.form.only_recent" /></el-form-item>
        <el-form-item v-if="profileDlg.form.only_recent" :label="t('web.sync.recent_limit')">
          <el-input-number v-model="profileDlg.form.recent_limit" :min="1" :max="200" />
        </el-form-item>
        <el-form-item :label="t('web.sync.enabled')"><el-switch v-model="profileDlg.form.enabled" /></el-form-item>
        <el-form-item :label="t('web.sync.dedup_priority')">
          <div class="prio-box">
            <div v-for="(k, i) in profileDlg.form.dedup_priority" :key="k" class="prio-chip">
              <span>{{ i + 1 }}. {{ kindLabel(k) }}</span>
              <el-icon class="prio-x" @click="prioRemove(k)"><Close /></el-icon>
            </div>
            <el-select
              v-if="profileDlg.pool.length"
              :model-value="''"
              size="small"
              :placeholder="t('web.sync.prio_add')"
              @change="prioAdd"
            >
              <el-option v-for="k in profileDlg.pool" :key="k" :label="kindLabel(k)" :value="k" />
            </el-select>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="profileDlg.visible = false">{{ t('web.sync.cancel') }}</el-button>
        <el-button type="primary" :loading="profileDlg.saving" @click="saveProfile">{{ t('web.sync.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Target dialog -->
    <el-dialog v-model="targetDlg.visible" :title="t('web.sync.target')" width="480px">
      <el-form :model="targetDlg.form" label-width="110px" size="default">
        <el-form-item :label="t('web.sync.kind')" required>
          <el-select v-model="targetDlg.form.kind" style="width: 100%" @change="onKindChange">
            <el-option v-for="k in ALL_KINDS" :key="k.value" :label="k.label" :value="k.value" />
          </el-select>
        </el-form-item>
        <template v-if="targetDlg.form.kind === 'playlist' || targetDlg.form.kind === 'channel'">
          <el-form-item :label="t('web.sync.url')" required>
            <el-input v-model="targetDlg.form.url" :placeholder="t('web.sync.url_ph')" />
          </el-form-item>
        </template>
        <el-alert v-else type="info" :closable="false" :title="t('web.sync.cookie_kind_hint')" />
        <el-form-item :label="t('web.sync.title')">
          <el-input v-model="targetDlg.form.title" :placeholder="t('web.sync.title_ph')" />
        </el-form-item>
        <el-form-item :label="t('web.sync.folder')">
          <el-input v-model="targetDlg.form.folder" :placeholder="t('web.sync.folder_ph')" />
        </el-form-item>
        <el-form-item :label="t('web.sync.enabled')"><el-switch v-model="targetDlg.form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="targetDlg.visible = false">{{ t('web.sync.cancel') }}</el-button>
        <el-button type="primary" :loading="targetDlg.saving" @click="saveTarget">{{ t('web.sync.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Close, FolderOpened } from '@element-plus/icons-vue'
import {
  listProfiles, getProfile, createProfile, updateProfile, deleteProfile,
  createTarget, updateTarget, deleteTarget, runSync,
} from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()

const KINDS = [
  { value: 'playlist', key: 'web.sync.kind_playlist' },
  { value: 'liked', key: 'web.sync.kind_liked' },
  { value: 'favorites', key: 'web.sync.kind_favorites' },
  { value: 'channel', key: 'web.sync.kind_channel' },
  { value: 'subscriptions', key: 'web.sync.kind_subs' },
]
const ALL_KINDS = [
  { value: 'liked', label: '❤️ ' + t('web.sync.kind_liked') },
  { value: 'favorites', label: '⭐ ' + t('web.sync.kind_favorites') },
  { value: 'playlist', label: '📁 ' + t('web.sync.kind_playlist') },
  { value: 'channel', label: '📺 ' + t('web.sync.kind_channel') },
  { value: 'subscriptions', label: '🌟 ' + t('web.sync.kind_subs') },
]

function kindLabel(k) {
  const hit = KINDS.find((x) => x.value === k)
  if (!hit) return k
  const s = t(hit.key)
  return { liked: '❤️ ' + s, favorites: '⭐ ' + s, playlist: '📁 ' + s, channel: '📺 ' + s, subscriptions: '🌟 ' + s }[k] || s
}

const profiles = ref([])
const targets = ref({})
const runningProfile = ref(null)

function targetsOf(pid) { return targets.value[pid] || [] }

async function load() {
  profiles.value = (await listProfiles()).profiles || []
  targets.value = {}
  for (const p of profiles.value) {
    const d = await getProfile(p.id)
    targets.value[p.id] = d.targets || []
  }
}

// ---- profile dialog ----------------------------------------------------

const profileDlg = reactive({ visible: false, id: null, form: {}, pool: [], saving: false })

function openProfile(p) {
  if (p) {
    profileDlg.id = p.id
    profileDlg.form = { ...p, dedup_priority: [...(p.dedup_priority || [])] }
    profileDlg.form.dedup_priority = Array.isArray(profileDlg.form.dedup_priority) ? profileDlg.form.dedup_priority : []
  } else {
    profileDlg.id = null
    profileDlg.form = {
      name: '', root_path: '', cookie_source: 'browser', cookie_browser: 'chrome',
      cookie_browser_profile: '', cookie_file_path: '', only_recent: false,
      recent_limit: 20, enabled: true,
      dedup_priority: ['liked', 'favorites', 'playlist', 'channel', 'subscriptions'],
    }
  }
  profileDlg.pool = ['liked', 'favorites', 'playlist', 'channel', 'subscriptions'].filter((k) => !profileDlg.form.dedup_priority.includes(k))
  profileDlg.visible = true
}

function prioRemove(k) {
  profileDlg.form.dedup_priority = profileDlg.form.dedup_priority.filter((x) => x !== k)
  profileDlg.pool = [...profileDlg.pool, k]
}
function prioAdd(k) {
  if (!k) return
  profileDlg.form.dedup_priority = [...profileDlg.form.dedup_priority, k]
  profileDlg.pool = profileDlg.pool.filter((x) => x !== k)
}

async function saveProfile() {
  profileDlg.saving = true
  try {
    if (profileDlg.id) await updateProfile(profileDlg.id, profileDlg.form)
    else await createProfile(profileDlg.form)
    profileDlg.visible = false
    ElMessage.success(t('web.sync.saved'))
    load()
  } catch (e) { ElMessage.error(errText(e)) } finally { profileDlg.saving = false }
}

async function removeProfile(p) {
  try {
    await ElMessageBox.confirm(t('web.sync.delete_profile_confirm'), t('web.sync.delete'), { type: 'warning' })
  } catch { return }
  try { await deleteProfile(p.id); load() } catch (e) { ElMessage.error(errText(e)) }
}

// ---- target dialog -----------------------------------------------------

const targetDlg = reactive({ visible: false, profileId: null, id: null, form: {}, saving: false })

function openTarget(p, tg) {
  targetDlg.profileId = p.id
  if (tg) {
    targetDlg.id = tg.id
    targetDlg.form = { ...tg }
  } else {
    targetDlg.id = null
    targetDlg.form = { kind: 'playlist', url: '', title: '', folder: '', enabled: true }
  }
  targetDlg.visible = true
}

function onKindChange(k) {
  // liked / favorites / subscriptions derive their URL from the engine defaults
  if (k === 'liked' || k === 'favorites' || k === 'subscriptions') targetDlg.form.url = ''
}

async function saveTarget() {
  targetDlg.saving = true
  try {
    if (targetDlg.id) await updateTarget(targetDlg.id, targetDlg.form)
    else await createTarget(targetDlg.profileId, targetDlg.form)
    targetDlg.visible = false
    ElMessage.success(t('web.sync.saved'))
    load()
  } catch (e) { ElMessage.error(errText(e)) } finally { targetDlg.saving = false }
}

async function toggleTarget(row, v) {
  try { await updateTarget(row.id, { enabled: v }) } catch (e) { ElMessage.error(errText(e)) }
}

async function removeTarget(row) {
  try {
    await ElMessageBox.confirm(t('web.sync.delete_target_confirm'), t('web.sync.delete'), { type: 'warning' })
  } catch { return }
  try { await deleteTarget(row.id); load() } catch (e) { ElMessage.error(errText(e)) }
}

// ---- run ---------------------------------------------------------------

async function runProfile(p) {
  runningProfile.value = p.id
  try {
    const r = await runSync(p.id)
    ElMessage.success(t('web.sync.run_done', { n: r.new }))
  } catch (e) { ElMessage.error(errText(e)) } finally { runningProfile.value = null }
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.head h3 { margin: 0; }
.profile-card { border: 1px solid var(--yts-border); border-radius: 8px; padding: 12px; margin-bottom: 14px; }
.profile-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.p-title { display: flex; align-items: center; gap: 8px; }
.p-name { font-weight: 600; }
.p-actions { display: flex; gap: 6px; }
.p-meta { display: flex; gap: 20px; color: var(--yts-text-dim); font-size: 12px; margin-bottom: 10px; }
.p-meta code { font-size: 11px; }
.url { color: var(--yts-text-dim); font-size: 12px; }
.prio-box { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.prio-chip { display: inline-flex; align-items: center; gap: 8px; background: rgba(201,0,0,0.10); padding: 4px 10px; border-radius: 6px; font-size: 13px; align-self: flex-start; }
.prio-x { cursor: pointer; color: var(--yts-text-dim); }
.prio-x:hover { color: #f56c6c; }
</style>