<template>
  <el-dialog v-model="visible" :title="t('time_range.title')" width="420px" @open="syncFromStore">
    <el-form label-width="100px">
      <el-form-item :label="t('time_range.start_time')">
        <el-input v-model="start" :placeholder="t('time_range.start_placeholder')" />
      </el-form-item>
      <el-form-item :label="t('time_range.end_time')">
        <el-input v-model="end" :placeholder="t('time_range.end_placeholder')" />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="keyframes">{{ t('time_range.force_keyframes') }}</el-checkbox>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button v-if="store.downloadSection" type="danger" text @click="clear">{{ t('buttons.clear') }}</el-button>
      <el-button @click="visible = false">{{ t('buttons.cancel') }}</el-button>
      <el-button type="primary" @click="apply">OK</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAnalysisStore } from '@/stores/analysis'

const { t } = useI18n()
const store = useAnalysisStore()
const visible = defineModel({ type: Boolean })

const start = ref('')
const end = ref('')
const keyframes = ref(true)

const TIME_RE = /^(\d{1,2}:)?\d{1,2}:\d{2}$/

function toSec(s) {
  const parts = s.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return parts[0] * 60 + parts[1]
}

function syncFromStore() {
  if (store.downloadSection) {
    const m = store.downloadSection.replace(/^\*/, '').split('-')
    start.value = m[0] || ''
    end.value = m[1] || ''
  } else {
    start.value = ''
    end.value = ''
  }
  keyframes.value = store.forceKeyframes
}

function apply() {
  if (!start.value && !end.value) {
    clear()
    return
  }
  if ((start.value && !TIME_RE.test(start.value)) || (end.value && !TIME_RE.test(end.value))) {
    ElMessage.warning(t('errors.invalid_speed_limit'))
    return
  }
  // Official: "*start-end" with either side optional
  store.downloadSection = `*${start.value || ''}-${end.value || ''}`
  store.forceKeyframes = keyframes.value
  visible.value = false
}

function clear() {
  store.downloadSection = null
  visible.value = false
}
</script>
