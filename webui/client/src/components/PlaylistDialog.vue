<template>
  <el-dialog v-model="visible" :title="t('playlist.select_videos_title')" width="640px" @open="syncFromStore">
    <div class="toolbar">
      <el-input v-model="filter" :placeholder="t('dialogs.filter_languages_placeholder')" clearable size="small" style="width: 220px" />
      <el-button size="small" @click="selectAll">{{ t('buttons.select_all') }}</el-button>
      <el-button size="small" @click="deselectAll">{{ t('buttons.deselect_all') }}</el-button>
      <span class="count">{{ t('subtitle_selection.count_selected', { count: checked.length }) }}</span>
    </div>
    <div class="entry-list">
      <el-checkbox-group v-model="checked">
        <el-checkbox
          v-for="e in filteredEntries"
          :key="e.index"
          :value="e.index"
          class="entry-item"
        >
          <span class="idx">{{ e.index }}.</span>
          {{ e.title || t('playlist.unknown') }}
          <span v-if="e.duration" class="dur">[{{ fmtDur(e.duration) }}]</span>
        </el-checkbox>
      </el-checkbox-group>
    </div>
    <template #footer>
      <el-button @click="visible = false">{{ t('buttons.close') }}</el-button>
      <el-button type="primary" @click="apply">{{ t('buttons.ok') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnalysisStore } from '@/stores/analysis'

const { t } = useI18n()
const store = useAnalysisStore()
const visible = defineModel({ type: Boolean })

const filter = ref('')
const checked = ref([])

const entries = computed(() =>
  store.playlistEntries.map((e, i) => ({ ...e, index: i + 1 }))
)
const filteredEntries = computed(() => {
  const f = filter.value.trim().toLowerCase()
  return f ? entries.value.filter((e) => (e.title || '').toLowerCase().includes(f)) : entries.value
})

function fmtDur(sec) {
  sec = Math.round(sec)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}

function syncFromStore() {
  checked.value = store.playlistAllSelected
    ? entries.value.map((e) => e.index)
    : [...store.playlistSelected]
}
function selectAll() { checked.value = entries.value.map((e) => e.index) }
function deselectAll() { checked.value = [] }
function apply() {
  const all = checked.value.length === entries.value.length
  store.playlistAllSelected = all
  store.playlistSelected = all ? [] : [...checked.value].sort((a, b) => a - b)
  visible.value = false
}
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
.count { margin-left: auto; color: var(--yts-text-dim); font-size: 13px; }
.entry-list { max-height: 380px; overflow-y: auto; }
.entry-item { display: block; height: 30px; margin-right: 0; }
.idx { color: var(--yts-text-dim); }
.dur { color: var(--yts-text-dim); font-size: 12px; margin-left: 6px; }
</style>
