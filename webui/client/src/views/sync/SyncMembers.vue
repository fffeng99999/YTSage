<template>
  <!--
    dysync parity: 关注列表 / 全体成员.
    Channels live per sync source, so the same author in two accounts shows up
    as two unrelated targets. This page folds them into one "member" row so a
    channel can be enabled, re-pathed, synced or deleted across every source
    at once.
  -->
  <div class="sync-members-page">
    <div class="head">
      <h3>{{ t('web.sync.members') }}</h3>
      <el-button size="small" :icon="Refresh" @click="load">{{ t('web.sync.refresh') }}</el-button>
    </div>

    <div v-if="selected.length" class="bulk">
      <span class="bulk-n">{{ t('web.sync.members_selected', { n: selected.length }) }}</span>
      <el-select v-model="bulkMode" size="small" style="width: 130px">
        <el-option :label="t('web.sync.sub_sync_off')" value="off" />
        <el-option :label="t('web.sync.sub_sync_on')" value="sync" />
        <el-option :label="t('web.sync.sub_sync_full')" value="full_sync" />
      </el-select>
      <el-button size="small" type="primary" @click="applyMode">{{ t('web.sync.members_set_mode') }}</el-button>
      <el-button size="small" @click="pathDlg.visible = true">{{ t('web.sync.members_set_path') }}</el-button>
      <el-button size="small" type="success" :loading="syncing" @click="syncSelected">{{ t('web.sync.members_sync') }}</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="members"
      size="small"
      style="width: 100%"
      @selection-change="(rows) => (selected = rows)"
    >
      <el-table-column type="selection" width="44" />
      <el-table-column :label="t('web.sync.member')" min-width="220">
        <template #default="{ row }">
          <div class="member">
            <img v-if="row.avatar_url" class="avatar" :src="row.avatar_url" alt="" />
            <div class="member-main">
              <div class="member-name">
                {{ row.name }}
                <el-tag v-if="row.is_members" size="small" type="warning">
                  {{ t('web.sync.members_only') }}
                </el-tag>
              </div>
              <div class="member-sub">
                {{ t('web.sync.member_sources', { n: row.profile_count || 0 }) }}
                <template v-if="row.target_count">· {{ row.target_count }} target(s)</template>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="video_count" :label="t('web.sync.stat_total_videos')" width="100" />
      <el-table-column :label="t('web.sync.col_size')" width="100">
        <template #default="{ row }">{{ fmtSize(row.total_size) }}</template>
      </el-table-column>
      <el-table-column :label="t('web.sync.member_mode')" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="modeType(row.sync_mode)">{{ modeLabel(row.sync_mode) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('web.sync.col_ops')" width="180">
        <template #default="{ row }">
          <el-button text size="small" @click="openVideos(row)">{{ t('web.sync.member_videos') }}</el-button>
          <el-button text size="small" type="danger" @click="removeMember(row)">{{ t('web.sync.delete') }}</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <span class="hint">{{ t('web.sync.no_members') }}</span>
      </template>
    </el-table>

    <el-dialog v-model="pathDlg.visible" :title="t('web.sync.members_set_path')" width="480px">
      <el-input v-model="pathDlg.path" :placeholder="t('web.sync.folder_ph')" />
      <template #footer>
        <el-button @click="pathDlg.visible = false">{{ t('web.sync.cancel') }}</el-button>
        <el-button type="primary" @click="applyPath">{{ t('web.sync.save') }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="videos.visible" :title="videos.name" size="60%">
      <el-table :data="videos.entries" size="small" max-height="100%">
        <el-table-column prop="video_title" :label="t('web.sync.title')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" :label="t('web.sync.col_status')" width="110" />
        <el-table-column :label="t('web.sync.col_size')" width="100">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  listMembers, setMembersSyncMode, setMembersSavePath, syncMembers,
  getMemberVideos, deleteMember,
} from '@/api/sync'
import { errText } from '@/api/http'

const { t } = useI18n()

const members = ref([])
const selected = ref([])
const loading = ref(false)
const syncing = ref(false)
const bulkMode = ref('sync')
const pathDlg = reactive({ visible: false, path: '' })
const videos = reactive({ visible: false, name: '', entries: [] })

function fmtSize(n) {
  const v = Number(n || 0)
  if (!v) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let s = v
  while (s >= 1024 && i < units.length - 1) { s /= 1024; i++ }
  return `${s.toFixed(1)} ${units[i]}`
}

function modeLabel(mode) {
  return { off: t('web.sync.sub_sync_off'), sync: t('web.sync.sub_sync_on'),
    full_sync: t('web.sync.sub_sync_full'), mixed: t('web.sync.member_mode_mixed'),
    none: '-' }[mode] || mode
}
function modeType(mode) {
  return { off: 'info', sync: 'success', full_sync: 'warning', mixed: 'warning' }[mode] || 'info'
}

function targetIds() {
  return selected.value.flatMap((m) => m.target_ids || [])
}

async function load() {
  loading.value = true
  try {
    members.value = (await listMembers()).members || []
  } catch (e) { ElMessage.error(errText(e)) } finally { loading.value = false }
}

async function applyMode() {
  const ids = targetIds()
  if (!ids.length) return ElMessage.info(t('web.sync.members_no_target'))
  try {
    const r = await setMembersSyncMode(ids, bulkMode.value)
    ElMessage.success(t('web.sync.saved') + ` (${r.updated})`)
    load()
  } catch (e) { ElMessage.error(errText(e)) }
}

async function applyPath() {
  const ids = targetIds()
  if (!ids.length || !pathDlg.path) return
  try {
    await setMembersSavePath(ids, pathDlg.path)
    pathDlg.visible = false
    ElMessage.success(t('web.sync.saved'))
    load()
  } catch (e) { ElMessage.error(errText(e)) }
}

async function syncSelected() {
  const ids = targetIds()
  if (!ids.length) return ElMessage.info(t('web.sync.members_no_target'))
  syncing.value = true
  try {
    await syncMembers(ids)
    ElMessage.success(t('web.sync.run_done', { n: ids.length }))
  } catch (e) { ElMessage.error(errText(e)) } finally { syncing.value = false }
}

async function openVideos(row) {
  videos.name = row.name
  videos.visible = true
  videos.entries = []
  try {
    videos.entries = (await getMemberVideos(row.name)).entries || []
  } catch (e) { ElMessage.error(errText(e)) }
}

async function removeMember(row) {
  try {
    await ElMessageBox.confirm(
      t('web.sync.member_delete_confirm', { n: row.name }),
      t('web.sync.delete'), { type: 'warning' }
    )
  } catch { return }
  try {
    await deleteMember(row.name)
    ElMessage.success(t('web.sync.saved'))
    load()
  } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.head h3 { margin: 0; }
.bulk { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.bulk-n { font-size: 13px; color: var(--yts-text-dim); }
.member { display: flex; align-items: center; gap: 10px; }
.avatar { width: 34px; height: 34px; border-radius: 50%; object-fit: cover; flex: none; }
.member-main { min-width: 0; }
.member-name { display: flex; align-items: center; gap: 6px; }
.member-sub { font-size: 12px; color: var(--yts-text-dim); }
.hint { color: var(--yts-text-dim); font-size: 12px; }
</style>
