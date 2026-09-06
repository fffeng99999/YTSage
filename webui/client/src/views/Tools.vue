<template>
  <div class="tools-page">
    <el-tabs v-model="tab">
      <!-- ============ Cookies ============ -->
      <el-tab-pane :label="t('tabs.cookies')" name="cookies">
        <div class="yts-card">
          <p class="help">{{ t('cookies.help_text') }}</p>
          <el-radio-group v-model="ck.source" style="margin-bottom: 14px">
            <el-radio value="browser">{{ t('cookies.extract_from_browser') }} ({{ t('cookies.recommended') }})</el-radio>
            <el-radio value="file">{{ t('cookies.use_cookie_file') }}</el-radio>
          </el-radio-group>

          <template v-if="ck.source === 'browser'">
            <el-form label-width="160px">
              <el-form-item :label="t('cookies.browser_label')">
                <el-select v-model="ck.browser" style="width: 200px">
                  <el-option v-for="b in browsers" :key="b" :label="b" :value="b" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('cookies.profile_label')">
                <el-input v-model="ck.profile" :placeholder="t('cookies.profile_placeholder')" style="width: 260px" />
              </el-form-item>
            </el-form>
          </template>
          <template v-else>
            <el-form label-width="160px">
              <el-form-item :label="t('web.cookie_content_label')">
                <el-input
                  v-model="ck.file_content"
                  type="textarea"
                  :rows="8"
                  :placeholder="t('web.cookie_content_placeholder')"
                  style="width: 560px"
                />
              </el-form-item>
              <el-form-item>
                <span class="help">{{ t('web.cookie_content_help') }}</span>
              </el-form-item>
            </el-form>
          </template>

          <el-checkbox v-model="ck.remember">{{ t('cookies.remember_settings') }}</el-checkbox>

          <div class="row">
            <el-tag :type="status.active ? 'success' : 'info'" style="margin-right: 12px">
              {{ status.active ? `${t('cookies.active_' + status.source)}: ${status.detail}` : t('cookies.none_active') }}
            </el-tag>
            <el-button type="primary" @click="applyCookies">{{ t('buttons.apply') }}</el-button>
            <el-button @click="clearCookies">{{ t('buttons.clear') }}</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ Custom Command ============ -->
      <el-tab-pane :label="t('tabs.custom_command')" name="command">
        <div class="yts-card">
          <p class="help">{{ t('custom_command.help_text') }}</p>
          <el-form label-width="160px">
            <el-form-item :label="t('custom_command.args_label')">
              <el-input v-model="cmd.command" :placeholder="t('custom_command.command_placeholder')" style="width: 560px" />
            </el-form-item>
            <el-form-item :label="t('custom_command.url_label')">
              <el-input v-model="cmd.url" :placeholder="t('main_ui.url_placeholder')" style="width: 560px" />
            </el-form-item>
          </el-form>
          <div class="row">
            <el-button type="primary" :loading="store.commandRunning" @click="runCmd">{{ t('command.run_command') }}</el-button>
            <el-button @click="store.clearCommandLog()">{{ t('buttons.clear') }}</el-button>
            <a :href="ytdlpDocs" target="_blank" class="doc-link">yt-dlp docs</a>
          </div>
          <div ref="consoleRef" class="console-output" style="margin-top: 12px">{{ commandText }}</div>
        </div>
      </el-tab-pane>

      <!-- ============ Proxy ============ -->
      <el-tab-pane :label="t('tabs.proxy')" name="proxy">
        <div class="yts-card">
          <p class="help">{{ t('proxy.help_text') }}</p>
          <el-form label-width="220px">
            <el-form-item :label="t('proxy.main_proxy')">
              <el-input v-model="px.proxy_url" :placeholder="t('proxy.proxy_url_placeholder')" style="width: 420px" :class="{ invalid: px.proxy_url && !validProxy(px.proxy_url) }" />
            </el-form-item>
            <el-form-item :label="t('proxy.geo_proxy')">
              <el-input v-model="px.geo_proxy_url" :placeholder="t('proxy.geo_bypass_placeholder')" style="width: 420px" :class="{ invalid: px.geo_proxy_url && !validProxy(px.geo_proxy_url) }" />
            </el-form-item>
            <el-form-item>
              <span class="help">{{ t('proxy.proxy_examples') }}</span>
            </el-form-item>
          </el-form>
          <div class="row">
            <el-button type="primary" @click="saveProxy">{{ t('settings.save_settings') }}</el-button>
            <el-button @click="px.proxy_url = ''">{{ t('proxy.clear_main_proxy') }}</el-button>
            <el-button @click="px.geo_proxy_url = ''">{{ t('proxy.clear_geo_proxy') }}</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ Language ============ -->
      <el-tab-pane :label="t('tabs.language')" name="language">
        <div class="yts-card">
          <p class="help">{{ t('language.current_language', { language: t('language.' + (lang === 'zh' ? 'chinese' : 'english')) }) }}</p>
          <el-select v-model="lang" style="width: 200px" @change="saveLang">
            <el-option label="English" value="en" />
            <el-option label="中文" value="zh" />
          </el-select>
          <p class="help" style="margin-top: 10px">{{ t('language.restart_required') }}</p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useDownloadStore } from '@/stores/download'
import { useSettingsStore } from '@/stores/settings'
import { applyCookies as apiApply, clearCookies as apiClear, cookiesStatus, cookiesContent } from '@/api/system'
import { runCommand } from '@/api/tools'
import { errText } from '@/api/http'
import { loadLocale } from '@/i18n'

const { t } = useI18n()
const store = useDownloadStore()
const settingsStore = useSettingsStore()

const tab = ref('cookies')
const browsers = ['chrome', 'firefox', 'safari', 'edge', 'opera', 'brave', 'chromium', 'vivaldi']
const ytdlpDocs = 'https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#usage-and-options'

const ck = ref({ source: 'browser', browser: 'chrome', profile: '', file_path: '', remember: true })
const status = ref({ active: false, source: 'browser', detail: null })
const cmd = ref({ command: '', url: '' })
const px = ref({ proxy_url: '', geo_proxy_url: '' })
const lang = ref('en')
const consoleRef = ref(null)

const commandText = computed(() => store.commandLines.join('\n'))

watch(commandText, async () => {
  await nextTick()
  if (consoleRef.value) consoleRef.value.scrollTop = consoleRef.value.scrollHeight
})

function validProxy(v) {
  return /^(https?|socks5(_hostd)?|socks4):\/\//.test(v)
}

async function loadStatus() {
  try { status.value = await cookiesStatus() } catch {}
}

async function applyCookies() {
  try {
    await apiApply(ck.value)
    ElMessage.success(ck.value.source === 'file' ? t('cookies.file_applied_message') : t('cookies.browser_applied_message'))
    loadStatus()
  } catch (e) { ElMessage.error(errText(e)) }
}
async function clearCookies() {
  await apiClear()
  ck.value.file_content = ''
  ElMessage.success(t('cookies.cleared_message'))
  loadStatus()
}

async function runCmd() {
  if (!cmd.value.command.trim()) { ElMessage.warning(t('custom_command.error_no_command')); return }
  store.clearCommandLog()
  try {
    await runCommand(cmd.value.command, cmd.value.url || null, null)
  } catch (e) { ElMessage.error(errText(e)) }
}

async function saveProxy() {
  if (px.value.proxy_url && !validProxy(px.value.proxy_url)) { ElMessage.error(t('proxy.invalid_main_url')); return }
  if (px.value.geo_proxy_url && !validProxy(px.value.geo_proxy_url)) { ElMessage.error(t('proxy.invalid_geo_url')); return }
  try {
    await settingsStore.save({ proxy_url: px.value.proxy_url || null, geo_proxy_url: px.value.geo_proxy_url || null })
    ElMessage.success(t('settings.settings_saved_successfully'))
  } catch (e) { ElMessage.error(errText(e)) }
}

async function saveLang(v) {
  try {
    await settingsStore.save({ language: v })
    await loadLocale(v)
  } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(async () => {
  await settingsStore.fetch()
  const s = settingsStore.settings || {}
  ck.value.source = s.cookie_source || 'browser'
  ck.value.browser = s.cookie_browser || 'chrome'
  ck.value.profile = s.cookie_browser_profile || ''
  ck.value.file_path = s.cookie_file_path || ''
  px.value.proxy_url = s.proxy_url || ''
  px.value.geo_proxy_url = s.geo_proxy_url || ''
  lang.value = s.language || 'en'
  loadStatus()
})
</script>

<style scoped>
.help { color: var(--yts-text-dim); font-size: 13px; }
.row { margin-top: 12px; display: flex; align-items: center; gap: 10px; }
.doc-link { color: var(--yts-red); font-size: 13px; }
:deep(.invalid .el-input__wrapper) { box-shadow: 0 0 0 1px var(--yts-red) inset; }
:deep(.el-tabs__item) { color: var(--yts-text-dim); }
:deep(.el-tabs__item.is-active) { color: var(--yts-red); }
:deep(.el-tabs__active-bar) { background-color: var(--yts-red); }
</style>
