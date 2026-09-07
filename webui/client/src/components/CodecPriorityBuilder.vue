<!--
  Codec priority builder (native HTML5 DnD, no new deps).

  modelValue is an ordered array of codec keys, e.g. ["av01","vp09","avc1"]
  meaning: prefer AV1, then VP9, then AVC. Left = pool (codecs NOT in the
  priority list), right = ordered priority sequence (drag to reorder, drag
  back to the pool to drop a codec). The batch/channel download pages read
  this list to pick formats and to build the yt-dlp codec-chain selector.
-->
<template>
  <div class="cp-builder">
    <div class="cp-cols">
      <div
        class="cp-pool"
        :class="{ 'cp-over': overPool }"
        @dragover.prevent="overPool = true"
        @dragleave="overPool = false"
        @drop.prevent="onDropPool($event)"
      >
        <div class="cp-label">{{ t('web.codec.pool') }}</div>
        <div class="cp-blocks">
          <div
            v-for="key in availableCodecs"
            :key="key"
            class="cp-block"
            draggable="true"
            @dragstart="onDragStart($event, { src: 'pool', key })"
          >{{ codecLabel(key) }}</div>
          <div v-if="!availableCodecs.length" class="cp-empty">{{ t('web.codec.pool_empty') }}</div>
        </div>
        <div class="cp-hint">{{ t('web.codec.hint_pool') }}</div>
      </div>

      <div class="cp-seq">
        <div class="cp-label">{{ t('web.codec.sequence') }}</div>
        <div class="cp-blocks cp-seq-blocks" @dragover.prevent @drop.prevent="onDropSeq($event, -1)">
          <template v-for="(key, i) in seq" :key="key">
            <div class="cp-gap" @dragover.prevent @drop.stop.prevent="onDropSeq($event, i)"></div>
            <div class="cp-block" draggable="true" @dragstart="onDragStart($event, { src: 'seq', idx: i })">
              <span class="cp-rank">{{ i + 1 }}</span>
              <span class="cp-block-label">{{ codecLabel(key) }}</span>
              <span class="cp-del" @click.stop="removeSeq(i)">×</span>
            </div>
          </template>
          <div v-if="!seq.length" class="cp-empty">{{ t('web.codec.empty') }}</div>
        </div>
        <div class="cp-hint">{{ t('web.codec.hint_seq') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: Array, default: () => ['av01', 'vp09', 'avc1'] },
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

const ALL_CODECS = ['av01', 'vp09', 'avc1']
const LABELS = { av01: 'AV1', vp09: 'VP9', avc1: 'AVC / H.264' }

function codecLabel(key) {
  return LABELS[key] || key
}

const seq = ref([...(props.modelValue || [])].filter((k) => ALL_CODECS.includes(k)))
const overPool = ref(false)
let dragPayload = null

const availableCodecs = computed(() => ALL_CODECS.filter((k) => !seq.value.includes(k)))

watch(seq, () => {
  emit('update:modelValue', [...seq.value])
}, { deep: true })

// Parent changed the array externally (e.g. loaded settings / reset): re-sync.
watch(() => props.modelValue, (v) => {
  const incoming = [...(v || [])].filter((k) => ALL_CODECS.includes(k))
  if (incoming.join(',') !== seq.value.join(',')) seq.value = incoming
})

function onDragStart(e, payload) {
  dragPayload = payload
  try {
    e.dataTransfer.setData('text/plain', JSON.stringify(payload))
    e.dataTransfer.effectAllowed = 'copyMove'
  } catch { /* ignore */ }
}

function readPayload(e) {
  if (dragPayload) return dragPayload
  try {
    return JSON.parse(e.dataTransfer.getData('text/plain')) || null
  } catch { return null }
}

function onDropSeq(e, at) {
  overPool.value = false
  const p = readPayload(e)
  dragPayload = null
  if (!p) return
  if (p.src === 'seq') {
    const from = p.idx
    if (from === at || from + 1 === at) return
    const [moved] = seq.value.splice(from, 1)
    const target = at > from ? at - 1 : at
    seq.value.splice(target < 0 ? seq.value.length : target, 0, moved)
  } else if (p.src === 'pool') {
    const insertAt = at < 0 ? seq.value.length : at
    seq.value.splice(insertAt, 0, p.key)
  }
}

function onDropPool(e) {
  overPool.value = false
  const p = readPayload(e)
  dragPayload = null
  if (p && p.src === 'seq') removeSeq(p.idx)
}

function removeSeq(i) {
  seq.value.splice(i, 1)
}
</script>

<style scoped>
.cp-builder { margin-top: 4px; }
.cp-cols { display: flex; gap: 14px; flex-wrap: wrap; }
.cp-pool, .cp-seq {
  border: 1px dashed var(--yts-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--yts-panel-2);
}
.cp-pool { flex: 0 0 220px; }
.cp-pool.cp-over { border-color: #ff6b6b; background: rgba(201, 0, 0, 0.08); }
.cp-seq { flex: 1; min-width: 300px; }
.cp-label { color: var(--yts-text-dim); font-size: 12px; margin-bottom: 8px; }
.cp-blocks { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-height: 34px; }
.cp-seq-blocks { min-height: 40px; }
.cp-block {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 6px; font-size: 13px;
  cursor: grab; user-select: none;
  background: rgba(201, 0, 0, 0.18); border: 1px solid rgba(255, 107, 107, 0.5); color: #ffb3b3;
}
.cp-rank {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%;
  background: #c90000; color: #fff; font-size: 11px; font-weight: 700;
}
.cp-del { opacity: 0.55; font-weight: 700; cursor: pointer; }
.cp-del:hover { opacity: 1; color: #ff6b6b; }
.cp-gap { width: 4px; height: 28px; border-radius: 2px; }
.cp-gap:hover { background: rgba(255, 107, 107, 0.4); }
.cp-empty { color: var(--yts-text-dim); font-size: 12px; padding: 6px; border: 1px dashed var(--yts-border); border-radius: 6px; }
.cp-hint { color: var(--yts-text-dim); font-size: 11px; margin-top: 8px; }
</style>
