<template>
  <el-dialog v-model="visible" :title="t('dialogs.select_subtitles')" width="520px" @open="syncFromStore">
    <el-input
      v-model="filter"
      :placeholder="t('dialogs.filter_languages_placeholder')"
      clearable
      size="small"
      style="margin-bottom: 10px"
    />
    <el-empty v-if="!subs.length" :description="t('dialogs.no_subtitles_available')" :image-size="60" />
    <div v-else class="sub-list">
      <el-checkbox-group v-model="selected">
        <el-checkbox v-for="s in filteredSubs" :key="s.value" :value="s.value" class="sub-item">
          {{ s.label }}
        </el-checkbox>
      </el-checkbox-group>
    </div>
    <el-checkbox v-model="merge" style="margin-top: 12px">{{ t('main_ui.merge_subtitles') }}</el-checkbox>
    <template #footer>
      <span class="dialog-count">{{ t('subtitle_selection.count_selected', { count: selected.length }) }}</span>
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
const selected = ref([])
const merge = ref(false)

const subs = computed(() =>
  (store.result?.subtitles || []).map((s) => {
    const value = s.type === 'auto' ? `${s.code} - Auto-generated` : s.code
    const label = s.type === 'auto' ? `${s.code} - Auto-generated` : `${s.code} - Manual`
    return { value, label }
  })
)
const filteredSubs = computed(() => {
  const f = filter.value.trim().toLowerCase()
  return f ? subs.value.filter((s) => s.label.toLowerCase().includes(f)) : subs.value
})

function syncFromStore() {
  selected.value = [...store.selectedSubtitles]
  merge.value = store.mergeSubs
  filter.value = ''
}

function apply() {
  store.selectedSubtitles = [...selected.value]
  store.mergeSubs = merge.value && selected.value.length > 0
  visible.value = false
}
</script>

<style scoped>
.sub-list {
  max-height: 300px;
  overflow-y: auto;
}
.sub-item {
  display: block;
  height: 28px;
  margin-right: 0;
}
.dialog-count {
  float: left;
  color: var(--yts-text-dim);
  line-height: 32px;
}
</style>
