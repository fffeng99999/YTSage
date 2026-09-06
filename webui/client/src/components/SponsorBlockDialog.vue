<template>
  <el-dialog v-model="visible" :title="t('dialogs.sponsorblock_categories')" width="560px" @open="syncFromStore">
    <p class="desc">{{ t('dialogs.sponsorblock_description') }}</p>
    <div class="cat-list">
      <div v-for="cat in categories" :key="cat.id" class="cat-row">
        <el-checkbox v-model="selected" :value="cat.id">
          <b>{{ t(`sponsorblock.${cat.id}`) }}</b>
          <span class="cat-desc"> — {{ t(`sponsorblock.${cat.id}_desc`) }}</span>
        </el-checkbox>
      </div>
    </div>
    <template #footer>
      <span class="dialog-count">{{ t('selection.count_selected', { count: selected.length }) }}</span>
      <el-button @click="visible = false">{{ t('buttons.close') }}</el-button>
      <el-button type="primary" @click="apply">{{ t('buttons.ok') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnalysisStore, SPONSORBLOCK_CATEGORIES } from '@/stores/analysis'

const { t } = useI18n()
const store = useAnalysisStore()
const visible = defineModel({ type: Boolean })

const categories = SPONSORBLOCK_CATEGORIES
const selected = ref([])

function syncFromStore() {
  selected.value = [...store.sponsorblockSelected]
}
function apply() {
  store.sponsorblockSelected = [...selected.value]
  visible.value = false
}
</script>

<style scoped>
.desc { color: var(--yts-text-dim); font-size: 13px; }
.cat-row { padding: 4px 0; }
.cat-desc { color: var(--yts-text-dim); font-size: 12px; }
.dialog-count { float: left; color: var(--yts-text-dim); line-height: 32px; }
</style>
