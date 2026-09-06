/**
 * Analysis store: holds current analysis result + all user selections that
 * mirror the official desktop GUI (format table, subtitles, SponsorBlock,
 * playlist item selection, time-range trim, embed options).
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { analyzeUrl } from '@/api/download'

// Official playlist preset table (ytsage_gui_format_table.py L349-360)
export const PLAYLIST_PRESETS = [
  { quality: 'Best Available', resolution: 'Max Quality', format_id: 'bestvideo+bestaudio/best' },
  { quality: '2160p (4K)', resolution: '≤ 3840x2160', format_id: 'bestvideo[height<=2160]+bestaudio/best/best[height<=2160]' },
  { quality: '1440p (2K)', resolution: '≤ 2560x1440', format_id: 'bestvideo[height<=1440]+bestaudio/best/best[height<=1440]' },
  { quality: '1080p (Full HD)', resolution: '≤ 1920x1080', format_id: 'bestvideo[height<=1080]+bestaudio/best/best[height<=1080]' },
  { quality: '720p (HD)', resolution: '≤ 1280x720', format_id: 'bestvideo[height<=720]+bestaudio/best/best[height<=720]' },
  { quality: '480p', resolution: '≤ 854x480', format_id: 'bestvideo[height<=480]+bestaudio/best/best[height<=480]' },
  { quality: '360p', resolution: '≤ 640x360', format_id: 'bestvideo[height<=360]+bestaudio/best/best[height<=360]' },
  { quality: '240p', resolution: '≤ 426x240', format_id: 'bestvideo[height<=240]+bestaudio/best/best[height<=240]' },
  { quality: '144p', resolution: '≤ 256x144', format_id: 'bestvideo[height<=144]+bestaudio/best/best[height<=144]' },
  { quality: 'Lowest Available', resolution: 'Worst Available', format_id: 'worstvideo+bestaudio/worst' },
]

// Official SponsorBlock categories (ytsage_dialogs_custom.py)
export const SPONSORBLOCK_CATEGORIES = [
  { id: 'sponsor', default: true },
  { id: 'selfpromo', default: true },
  { id: 'interaction', default: true },
  { id: 'intro', default: false },
  { id: 'outro', default: false },
  { id: 'preview', default: false },
  { id: 'music_offtopic', default: false },
  { id: 'filler', default: false },
]

function condenseIndices(indices) {
  // Official _condense_indices: [1,2,3,5,7,8] -> "1-3,5,7-8"
  if (!indices.length) return null
  const sorted = [...new Set(indices)].sort((a, b) => a - b)
  const parts = []
  let start = sorted[0], prev = sorted[0]
  for (let i = 1; i <= sorted.length; i++) {
    if (i < sorted.length && sorted[i] === prev + 1) { prev = sorted[i]; continue }
    parts.push(start === prev ? `${start}` : `${start}-${prev}`)
    if (i < sorted.length) { start = prev = sorted[i] }
  }
  return parts.join(',')
}

export const useAnalysisStore = defineStore('analysis', () => {
  const result = ref(null)          // full analysis payload
  const analyzing = ref(false)
  const analyzeStage = ref('')      // i18n key for progress text

  // Format selection (single video mode)
  const selectedVideoFormat = ref(null)   // format dict
  const selectedAudioFormats = ref([])    // format dicts (multi)
  const mode = ref('video')               // 'video' | 'audio' filter

  // Playlist selection
  const playlistSelected = ref([])        // 1-based indices
  const playlistAllSelected = ref(true)

  // Subtitles: array of "code" or "code - Auto-generated" strings
  const selectedSubtitles = ref([])
  const mergeSubs = ref(false)

  // SponsorBlock
  const sponsorblockSelected = ref(SPONSORBLOCK_CATEGORIES.filter(c => c.default).map(c => c.id))

  // Options
  const saveThumbnail = ref(false)
  const saveDescription = ref(false)
  const embedChapters = ref(false)
  const embedMetadata = ref(false)
  const embedThumbnail = ref(false)

  // Time range
  const downloadSection = ref(null)   // "*HH:MM:SS-HH:MM:SS"
  const forceKeyframes = ref(true)

  const isPlaylist = computed(() => !!result.value?.is_playlist)
  const videoSummary = computed(() => result.value?.video_summary || {})
  const playlistEntries = computed(() => result.value?.playlist_entries || [])
  const formats = computed(() => result.value?.all_formats || [])

  // Official sort: video by resolution desc, audio by bitrate desc
  // (ytsage_gui_format_table.py L276-292 get_quality + reverse=True)
  const videoRows = computed(() =>
    formats.value
      .filter(f => f.vcodec && f.vcodec !== 'none')
      .sort((a, b) => (b.height || 0) - (a.height || 0))
  )
  const audioRows = computed(() =>
    formats.value
      .filter(f => (!f.vcodec || f.vcodec === 'none') && f.acodec && f.acodec !== 'none')
      .sort((a, b) => (b.abr || 0) - (a.abr || 0))
  )

  const playlistItemsString = computed(() => {
    if (!isPlaylist.value) return null
    if (playlistAllSelected.value || !playlistSelected.value.length) return null
    return condenseIndices(playlistSelected.value)
  })

  /** Build the /api/download payload core fields (selection part). */
  function buildDownloadSelection() {
    if (isPlaylist.value) {
      const preset = selectedVideoFormat.value
      if (mode.value === 'audio') {
        return { is_playlist: true, is_audio_only: true, format_id: null, resolution: '' }
      }
      return {
        is_playlist: true,
        is_audio_only: false,
        format_id: preset ? preset.format_id : null,
        resolution: '',
        playlist_items: playlistItemsString.value,
      }
    }
    if (mode.value === 'audio' || (!selectedVideoFormat.value && selectedAudioFormats.value.length)) {
      // audio-only: first selected audio row
      const a = selectedAudioFormats.value[0]
      if (!a) return null
      return {
        is_playlist: false, is_audio_only: true,
        format_id: a.format_id,
        format_has_audio: false,
        audio_format_ids: selectedAudioFormats.value.slice(1).map(f => f.format_id),
      }
    }
    const v = selectedVideoFormat.value
    if (!v) return null
    return {
      is_playlist: false,
      is_audio_only: false,
      format_id: v.format_id,
      format_has_audio: !!(v.acodec && v.acodec !== 'none'),
      audio_format_ids: selectedAudioFormats.value.map(f => f.format_id),
    }
  }

  async function analyze(url) {
    analyzing.value = true
    analyzeStage.value = 'main_ui.analyzing_extracting_detailed'
    reset()
    try {
      result.value = await analyzeUrl({ url })
      applyDefaults()
      return result.value
    } finally {
      analyzing.value = false
      analyzeStage.value = ''
    }
  }

  function applyDefaults() {
    // Auto-select best/default video format (official: default_video_quality)
    const settings = JSON.parse(localStorage.getItem('ytsage_settings_cache') || '{}')
    const dq = settings.default_video_quality
    const rows = videoRows.value
    if (rows.length) {
      let pick = null
      if (dq) pick = rows.find(f => String(f.height) === String(dq))
      if (!pick) pick = [...rows].sort((a, b) => (b.height || 0) - (a.height || 0))[0]
      selectedVideoFormat.value = pick
    }
    // Default subtitle language preselection
    const dsl = settings.default_subtitle_language
    if (dsl && result.value?.subtitles) {
      const langs = dsl.split(',').map(s => s.trim()).filter(Boolean)
      selectedSubtitles.value = result.value.subtitles
        .filter(s => langs.includes(s.code))
        .map(s => s.type === 'auto' ? `${s.code} - Auto-generated` : s.code)
    }
  }

  function reset() {
    result.value = null
    selectedVideoFormat.value = null
    selectedAudioFormats.value = []
    mode.value = 'video'
    playlistSelected.value = []
    playlistAllSelected.value = true
    selectedSubtitles.value = []
    mergeSubs.value = false
    sponsorblockSelected.value = SPONSORBLOCK_CATEGORIES.filter(c => c.default).map(c => c.id)
    saveThumbnail.value = false
    saveDescription.value = false
    embedChapters.value = false
    embedMetadata.value = false
    embedThumbnail.value = false
    downloadSection.value = null
  }

  /** Rehydrate from a history entry (redownload). */
  function loadSelectionFromOptions(opts) {
    if (!opts) return
    if (opts.subtitle_langs) selectedSubtitles.value = opts.subtitle_langs
    if (opts.merge_subs !== undefined) mergeSubs.value = !!opts.merge_subs
    if (opts.sponsorblock_categories) sponsorblockSelected.value = opts.sponsorblock_categories
    if (opts.save_description !== undefined) saveDescription.value = !!opts.save_description
    if (opts.embed_chapters !== undefined) embedChapters.value = !!opts.embed_chapters
    if (opts.embed_metadata !== undefined) embedMetadata.value = !!opts.embed_metadata
    if (opts.embed_thumbnail !== undefined) embedThumbnail.value = !!opts.embed_thumbnail
    if (opts.download_section) downloadSection.value = opts.download_section
    if (opts.force_keyframes !== undefined) forceKeyframes.value = !!opts.force_keyframes
  }

  return {
    result, analyzing, analyzeStage, mode,
    selectedVideoFormat, selectedAudioFormats,
    playlistSelected, playlistAllSelected, playlistItemsString,
    selectedSubtitles, mergeSubs, sponsorblockSelected,
    saveThumbnail, saveDescription, embedChapters, embedMetadata, embedThumbnail,
    downloadSection, forceKeyframes,
    isPlaylist, videoSummary, playlistEntries, formats, videoRows, audioRows,
    analyze, reset, buildDownloadSelection, loadSelectionFromOptions,
  }
})
