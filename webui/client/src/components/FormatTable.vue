<template>
  <div>
    <div class="fmt-toolbar">
      <span class="lbl">{{ t('formats.show_formats') }}:</span>
      <el-button-group>
        <el-button :type="mode === 'video' ? 'primary' : ''" size="small" @click="setMode('video')">
          {{ t('buttons.video') }}
        </el-button>
        <el-button :type="mode === 'audio' ? 'primary' : ''" size="small" @click="setMode('audio')">
          {{ t('buttons.audio_only') }}
        </el-button>
      </el-button-group>
    </div>

    <!-- Playlist mode: hardcoded preset table -->
    <el-table
      v-if="isPlaylist && mode === 'video'"
      :data="presets"
      highlight-current-row
      max-height="360"
      size="small"
      @current-change="onPresetSelect"
      class="yts-table"
    >
      <el-table-column width="46">
        <template #header>{{ t('formats.select') }}</template>
        <template #default="{ row }">
          <el-radio :model-value="selectedPreset" :label="row.format_id" @change="onPresetSelect(row)"><span /></el-radio>
        </template>
      </el-table-column>
      <el-table-column :label="t('formats.quality')" min-width="140">
        <template #default="{ row }"><span :class="qualityClass(presetLabel(row))">{{ presetLabel(row) }}</span></template>
      </el-table-column>
      <el-table-column :label="t('formats.resolution')" min-width="120">
        <template #default="{ row }">{{ presetResLabel(row) }}</template>
      </el-table-column>
    </el-table>

    <!-- Single video mode: full format table -->
    <el-table
      v-else
      :data="visibleRows"
      max-height="360"
      size="small"
      class="yts-table"
      @row-click="onRowClick"
    >
      <el-table-column width="46">
        <template #header>{{ t('formats.select') }}</template>
        <template #default="{ row }">
          <el-radio
            v-if="isVideoRow(row)"
            :model-value="selectedVideoId"
            :label="row.format_id"
            @change="selectVideo(row)"
          ><span /></el-radio>
          <el-checkbox
            v-else
            :model-value="selectedAudioIds.includes(row.format_id)"
            @change="(v) => toggleAudio(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column :label="t('formats.quality')" min-width="90">
        <template #default="{ row }"><span :class="qualityClass(row)">{{ qualityLabel(row) }}</span></template>
      </el-table-column>
      <el-table-column :label="t('formats.extension')" width="80">
        <template #default="{ row }">{{ row.ext || '-' }}</template>
      </el-table-column>
      <el-table-column :label="t('formats.resolution')" min-width="100">
        <template #default="{ row }">{{ resLabel(row) }}</template>
      </el-table-column>
      <el-table-column :label="t('formats.file_size')" width="90">
        <template #default="{ row }">{{ sizeLabel(row) }}</template>
      </el-table-column>
      <el-table-column :label="t('formats.codec')" min-width="120">
        <template #default="{ row }">{{ codecLabel(row) }}</template>
      </el-table-column>
      <el-table-column :label="t('formats.audio')" min-width="120">
        <template #default="{ row }">
          <span v-if="isVideoRow(row) && hasAudio(row)" class="lang-tag">{{ t('formats.has_audio') }}</span>
          <span v-else-if="isVideoRow(row)" class="merge-audio">{{ t('formats.will_merge_audio') }}</span>
          <span v-else>{{ row.abr ? row.abr + 'k' : (row.acodec || '') }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('formats.language')" width="90">
        <template #default="{ row }"><span class="lang-tag">{{ row.language || '-' }}</span></template>
      </el-table-column>
      <el-table-column :label="t('formats.fps')" width="70">
        <template #default="{ row }">
          <span :class="fpsClass(row.fps)">{{ row.fps || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('formats.hdr')" width="80">
        <template #default="{ row }">
          <span :class="hdrClass(row)">{{ hdrLabel(row) }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnalysisStore, PLAYLIST_PRESETS } from '@/stores/analysis'

const { t, te } = useI18n()
const store = useAnalysisStore()

const isPlaylist = computed(() => store.isPlaylist)
const mode = computed(() => store.mode)
const presets = PLAYLIST_PRESETS
const selectedPreset = computed(() => store.selectedVideoFormat?.format_id)
const selectedVideoId = computed(() => store.selectedVideoFormat?.format_id)
const selectedAudioIds = computed(() => store.selectedAudioFormats.map(f => f.format_id))

const visibleRows = computed(() =>
  mode.value === 'video' ? store.videoRows : store.audioRows
)

function isVideoRow(row) {
  return row.vcodec && row.vcodec !== 'none'
}
// Localized preset labels (fall back to the English fields for unknown keys)
function presetLabel(row) {
  return row.ikey && te(`web.presets.${row.ikey}`) ? t(`web.presets.${row.ikey}`) : row.quality
}
function presetResLabel(row) {
  return row.ikey && te(`web.presetsRes.${row.ikey}`) ? t(`web.presetsRes.${row.ikey}`) : row.resolution
}
function hasAudio(row) {
  return row.acodec && row.acodec !== 'none'
}

function setMode(m) {
  store.mode = m
}

function selectVideo(row) {
  store.selectedVideoFormat = row
}
function toggleAudio(row, checked) {
  if (checked) {
    if (!store.selectedAudioFormats.find(f => f.format_id === row.format_id)) {
      store.selectedAudioFormats.push(row)
    }
  } else {
    store.selectedAudioFormats = store.selectedAudioFormats.filter(f => f.format_id !== row.format_id)
  }
}
function onRowClick(row) {
  if (isVideoRow(row)) selectVideo(row)
  else toggleAudio(row, !selectedAudioIds.value.includes(row.format_id))
}
function onPresetSelect(row) {
  store.selectedVideoFormat = row
}

// ---- display helpers (official color rules) ----
function qualityLabel(row) {
  if (typeof row === 'string' || row.quality) return row.quality || ''
  const h = row.height || 0
  if (mode.value === 'audio') {
    const abr = row.abr || 0
    if (abr >= 160) return t('formats.best_audio')
    if (abr >= 128) return t('formats.high_audio')
    if (abr >= 96) return t('formats.medium_audio')
    return t('formats.low_audio')
  }
  if (h >= 2160) return t('formats.best_4k')
  if (h >= 1440) return t('formats.best_2k')
  if (h >= 1080) return t('formats.high_1080p')
  if (h >= 720) return t('formats.high_720p')
  if (h >= 480) return t('formats.medium_480p')
  return t('formats.low_quality')
}
function qualityClass(row) {
  const q = qualityLabel(row)
  if (/4K|2K|Best|最佳/i.test(q)) return 'q-best'
  if (/1080|720|High|高/i.test(q)) return 'q-high'
  if (/480|Medium|中/i.test(q)) return 'q-medium'
  return 'q-low'
}
function resLabel(row) {
  if (row.resolution) return row.resolution
  if (!row.height) return t('formats.audio_only_resolution')
  return row.width ? `${row.width}x${row.height}` : `${row.height}p`
}
function sizeLabel(row) {
  const b = row.filesize || row.filesize_approx
  if (!b) return '-'
  if (b > 1e9) return (b / 1e9).toFixed(2) + ' GB'
  if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB'
  return (b / 1e3).toFixed(0) + ' KB'
}
function codecLabel(row) {
  const v = row.vcodec && row.vcodec !== 'none' ? row.vcodec.split('.')[0] : ''
  const a = row.acodec && row.acodec !== 'none' ? row.acodec.split('.')[0] : ''
  return [v, a].filter(Boolean).join(' / ') || '-'
}
function fpsClass(fps) {
  if (!fps) return ''
  if (fps >= 60) return 'fps-high'
  if (fps >= 30) return 'fps-mid'
  return 'fps-low'
}
function hdrLabel(row) {
  const d = row.dynamic_range
  if (!d) return 'N/A'
  return d === 'SDR' ? 'SDR' : d
}
function hdrClass(row) {
  const d = row.dynamic_range
  return d && d !== 'SDR' ? 'hdr-tag' : ''
}
</script>

<style scoped>
.fmt-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.fmt-toolbar .lbl {
  color: var(--yts-text-dim);
  font-size: 13px;
}
.yts-table {
  background: transparent;
}
:deep(.yts-table), :deep(.el-table__inner-wrapper) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #1d1e22;
  --el-table-border-color: #3d3d3d;
  --el-table-row-hover-bg-color: #2a2f31;
  --el-table-text-color: #e8e8e8;
  --el-table-header-text-color: #c8c8c8;
}
</style>
