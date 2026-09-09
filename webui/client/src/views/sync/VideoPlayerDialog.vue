<template>
  <el-dialog
    v-model="visible"
    :title="t('web.sync.video_player')"
    width="720px"
    destroy-on-close
    append-to-body
    @closed="onClosed"
  >
    <div v-if="record" class="player-meta">
      <div class="pm-title">{{ record.video_title || record.video_id }}</div>
      <div class="pm-sub">
        <span>{{ record.channel || '-' }}</span>
        <span v-if="record.size">· {{ fmtSize(record.size) }}</span>
        <span>· {{ t('web.sync.streaming') }}</span>
      </div>
    </div>
    <video
      v-if="visible && src"
      ref="videoRef"
      class="player"
      controls
      autoplay
      :src="src"
      @error="onError"
    />
    <el-alert v-if="errored" type="error" :closable="false" :title="t('web.sync.play_error')" style="margin-top: 10px" />
    <template #footer>
      <el-button @click="visible = false">{{ t('web.sync.close_player') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { getVideoStreamUrl } from '@/api/sync'

const props = defineProps({ record: { type: Object, default: null } })
const visible = defineModel({ type: Boolean, default: false })

const { t } = useI18n()
const videoRef = ref(null)
const errored = ref(false)

const src = computed(() => {
  if (!props.record || !props.record.video_id) return ''
  return getVideoStreamUrl(props.record.video_id)
})

function onError() { errored.value = true }
function onClosed() { errored.value = false }

function fmtSize(bytes) {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++ }
  return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`
}
</script>

<style scoped>
.player { width: 100%; max-height: 60vh; background: #000; border-radius: 8px; }
.player-meta { margin-bottom: 10px; }
.pm-title { font-size: 15px; font-weight: 600; color: var(--yts-text); }
.pm-sub { margin-top: 4px; font-size: 12px; color: var(--yts-text-dim); display: flex; gap: 6px; }
</style>
