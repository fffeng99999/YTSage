<template>
  <div class="video-card yts-fade-in" v-if="store.result">
    <div class="thumb">
      <img v-if="thumbSrc" :src="thumbSrc" alt="thumbnail" />
      <div v-else class="thumb-placeholder">📹</div>
    </div>
    <div class="details">
      <h3 class="title">{{ displayTitle }}</h3>
      <template v-if="store.isPlaylist">
        <p class="meta">{{ t('playlist.total_videos', { count: store.playlistEntries.length }) }}</p>
      </template>
      <template v-else>
        <p class="meta">{{ t('video_info.channel') }}: {{ summary.channel || t('video_info.unknown_channel') }}</p>
        <p class="meta" v-if="summary.view_count != null">{{ t('video_info.views') }}: {{ Number(summary.view_count).toLocaleString() }}</p>
        <p class="meta" v-if="summary.like_count != null">{{ t('video_info.likes') }}: {{ Number(summary.like_count).toLocaleString() }}</p>
        <p class="meta" v-if="summary.upload_date">{{ t('video_info.upload_date') }}: {{ fmtDate(summary.upload_date) }}</p>
        <p class="meta">{{ t('video_info.duration') }}: {{ summary.duration_string || fmtDur(summary.duration) }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnalysisStore } from '@/stores/analysis'

const { t } = useI18n()
const store = useAnalysisStore()

const summary = computed(() => store.videoSummary)
const displayTitle = computed(() =>
  store.isPlaylist
    ? (store.result?.playlist_info?.title || t('playlist.unknown'))
    : (summary.value.title || t('video_info.unknown_title'))
)
const thumbSrc = computed(() => {
  const url = store.result?.thumbnail_url || summary.value.thumbnail
  return url ? `/api/thumbnail?url=${encodeURIComponent(url)}` : ''
})

function fmtDate(d) {
  if (!d || d.length < 8) return t('video_info.unknown_date')
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}
function fmtDur(sec) {
  if (!sec) return '-'
  sec = Math.round(sec)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.video-card {
  display: flex;
  gap: 16px;
}
.thumb {
  flex: 0 0 320px;
  height: 180px;
  border: 2px solid var(--yts-border);
  border-radius: 8px;
  overflow: hidden;
  background: #101214;
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-placeholder { font-size: 48px; opacity: 0.4; }
.details { flex: 1; min-width: 0; }
.title { margin: 0 0 8px; font-size: 16px; word-break: break-word; }
.meta { margin: 3px 0; color: var(--yts-text-dim); font-size: 13px; }
@media (max-width: 768px) {
  .video-card { flex-direction: column; }
  .thumb { flex: none; width: 100%; }
}
</style>
