<template>
  <div class="embed-panel">
    <el-checkbox v-model="store.embedChapters">{{ t('web.chapters') }}</el-checkbox>
    <el-checkbox v-model="store.embedMetadata">{{ t('web.metadata') }}</el-checkbox>
    <el-checkbox v-model="store.embedThumbnail">{{ t('web.thumbnail') }}</el-checkbox>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useAnalysisStore } from '@/stores/analysis'
const { t } = useI18n()
const store = useAnalysisStore()
</script>

<style scoped>
.embed-panel { display: flex; flex-direction: column; gap: 2px; }
</style>
