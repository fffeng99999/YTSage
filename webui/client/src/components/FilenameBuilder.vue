<!--
  Drag-and-drop filename format builder (native HTML5 DnD, no new deps).

  Left = block pool (wildcard tokens not yet used + a reusable "text" block).
  Right = ordered sequence; sequence order IS the filename order. Dropping a
  block back on the pool (or clicking x) removes it. The combined yt-dlp
  template is emitted live so the parent's plain input stays in sync.
-->
<template>
  <div class="fn-builder">
    <div class="fn-cols">
      <div
        class="fn-pool"
        :class="{ 'fn-over': overPool }"
        @dragover.prevent="overPool = true"
        @dragleave="overPool = false"
        @drop.prevent="onDropPool"
      >
        <div class="fn-label">{{ t('web.filename.pool') }}</div>
        <div class="fn-blocks">
          <div
            v-for="key in availableTokens"
            :key="key"
            class="fn-block fn-token"
            draggable="true"
            @dragstart="onDragStart($event, { src: 'pool', key })"
          >{{ tkLabel(key) }}</div>
          <div
            class="fn-block fn-text"
            draggable="true"
            @dragstart="onDragStart($event, { src: 'newtext' })"
          >+ {{ t('web.filename.text') }}</div>
        </div>
        <div class="fn-hint">{{ t('web.filename.hint_pool') }}</div>
      </div>

      <div class="fn-seq">
        <div class="fn-label">{{ t('web.filename.sequence') }}</div>
        <div class="fn-blocks fn-seq-blocks" @dragover.prevent @drop.prevent="onDropSeq(-1)">
          <template v-for="(item, i) in seq" :key="i">
            <div class="fn-gap" @dragover.prevent @drop.stop.prevent="onDropSeq(i)"></div>
            <div
              class="fn-block"
              :class="item.type === 'token' ? 'fn-token' : 'fn-text'"
              draggable="true"
              @dragstart="onDragStart($event, { src: 'seq', idx: i })"
            >
              <input
                v-if="editing === i"
                ref="editInput"
                v-model="item.value"
                class="fn-edit"
                @blur="editing = -1"
                @keyup.enter="editing = -1"
              />
              <span v-else class="fn-block-label" @dblclick="startEdit(i, item)">
                {{ item.type === 'token' ? tkLabel(item.key) : (item.value || '␣') }}
              </span>
              <span class="fn-del" @click.stop="removeSeq(i)">×</span>
            </div>
          </template>
          <div v-if="!seq.length" class="fn-empty">{{ t('web.filename.empty') }}</div>
        </div>
        <div class="fn-hint">{{ t('web.filename.hint_seq') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])

const { t, te } = useI18n()

const TOKEN_KEYS = ['title', 'uploader', 'upload_date', 'resolution', 'id', 'ext']
const TOKEN_RE = /%\((\w+)\)s/g

function tkLabel(key) {
  const k = `web.filename.tokens.${key}`
  return te(k) ? t(k) : `%(${key})s`
}

/** Parse a yt-dlp output template into an ordered list of blocks. */
function parseTemplate(str) {
  const items = []
  let last = 0
  let m
  TOKEN_RE.lastIndex = 0
  while ((m = TOKEN_RE.exec(str || '')) !== null) {
    if (m.index > last) items.push({ type: 'text', value: str.slice(last, m.index) })
    if (TOKEN_KEYS.includes(m[1])) items.push({ type: 'token', key: m[1] })
    else items.push({ type: 'text', value: m[0] }) // unknown token kept verbatim
    last = m.index + m[0].length
  }
  if (last < (str || '').length) items.push({ type: 'text', value: str.slice(last) })
  return items
}

function renderTemplate(items) {
  return items
    .map((it) => (it.type === 'token' ? `%(${it.key})s` : it.value))
    .join('')
}

const seq = ref(parseTemplate(props.modelValue))
const editing = ref(-1)
const editInput = ref(null)
const overPool = ref(false)
let dragPayload = null
let lastEmitted = props.modelValue || ''

const availableTokens = computed(
  () => TOKEN_KEYS.filter((k) => !seq.value.some((it) => it.type === 'token' && it.key === k))
)

watch(seq, () => {
  const out = renderTemplate(seq.value)
  if (out !== lastEmitted) {
    lastEmitted = out
    emit('update:modelValue', out)
  }
}, { deep: true })

// Parent (plain input / reset button / loaded settings) changed the string:
// re-parse into blocks unless the change came from us.
watch(() => props.modelValue, (v) => {
  if ((v || '') === lastEmitted) return
  lastEmitted = v || ''
  seq.value = parseTemplate(v)
})

function onDragStart(e, payload) {
  dragPayload = payload
  try {
    e.dataTransfer.setData('text/plain', JSON.stringify(payload))
    e.dataTransfer.effectAllowed = 'copyMove'
  } catch { /* older browsers */ }
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
  if (!p) return
  if (p.src === 'seq') {
    const from = p.idx
    if (from === at || from + 1 === at) return
    const [moved] = seq.value.splice(from, 1)
    const target = at > from ? at - 1 : at
    seq.value.splice(target, 0, moved)
  } else if (p.src === 'pool') {
    const insertAt = at < 0 ? seq.value.length : at
    seq.value.splice(insertAt, 0, { type: 'token', key: p.key })
  } else if (p.src === 'newtext') {
    const insertAt = at < 0 ? seq.value.length : at
    seq.value.splice(insertAt, 0, { type: 'text', value: '' })
    editing.value = insertAt
    nextTick(() => {
      const el = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
      el?.focus?.()
    })
  }
  dragPayload = null
}

function onDropPool(e) {
  overPool.value = false
  const p = readPayload(e)
  dragPayload = null
  if (p && p.src === 'seq') removeSeq(p.idx)
}

function removeSeq(i) {
  if (editing.value === i) editing.value = -1
  else if (editing.value > i) editing.value -= 1
  seq.value.splice(i, 1)
}

function startEdit(i, item) {
  if (item.type !== 'text') return
  editing.value = i
  nextTick(() => {
    const el = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
    el?.focus?.()
  })
}
</script>

<style scoped>
.fn-builder { margin-top: 10px; }
.fn-cols { display: flex; gap: 14px; flex-wrap: wrap; }
.fn-pool, .fn-seq {
  border: 1px dashed var(--yts-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--yts-panel-2);
}
.fn-pool { flex: 0 0 260px; }
.fn-pool.fn-over { border-color: #ff6b6b; background: rgba(201, 0, 0, 0.08); }
.fn-seq { flex: 1; min-width: 320px; }
.fn-label { color: var(--yts-text-dim); font-size: 12px; margin-bottom: 8px; }
.fn-blocks { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-height: 34px; }
.fn-seq-blocks { min-height: 40px; }
.fn-block {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 6px; font-size: 13px;
  cursor: grab; user-select: none;
}
.fn-token { background: rgba(201, 0, 0, 0.18); border: 1px solid rgba(255, 107, 107, 0.5); color: #ffb3b3; }
.fn-text { background: rgba(64, 158, 255, 0.15); border: 1px solid rgba(64, 158, 255, 0.5); color: #9ecbff; }
.fn-del { opacity: 0.55; font-weight: 700; cursor: pointer; margin-left: 2px; }
.fn-del:hover { opacity: 1; color: #ff6b6b; }
.fn-gap { width: 4px; height: 26px; border-radius: 2px; }
.fn-gap:hover { background: rgba(255, 107, 107, 0.4); }
.fn-empty { color: var(--yts-text-dim); font-size: 12px; padding: 6px; border: 1px dashed var(--yts-border); border-radius: 6px; }
.fn-hint { color: var(--yts-text-dim); font-size: 11px; margin-top: 8px; }
.fn-edit { width: 70px; background: transparent; border: none; border-bottom: 1px solid #9ecbff; color: inherit; font-size: 13px; outline: none; }
</style>
