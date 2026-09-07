<template>
  <div class="settings-page">
    <el-tabs v-model="tab">
      <!-- ============ General ============ -->
      <el-tab-pane :label="t('settings.tab_general')" name="general">
        <div class="yts-card">
          <el-form label-width="220px">
            <el-form-item :label="t('settings.download_path')">
              <el-input v-model="form.download_path" style="width: 420px" />
            </el-form-item>
            <el-form-item :label="t('settings.speed_limit')">
              <el-input v-model="form.speed_limit_value" :placeholder="t('settings.speed_limit_placeholder')" style="width: 140px" clearable />
              <el-select v-model="form.speed_limit_unit_index" style="width: 110px; margin-left: 8px">
                <el-option label="KB/s" :value="0" />
                <el-option label="MB/s" :value="1" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('settings.concurrent_fragments')">
              <el-tooltip :content="t('settings.concurrent_fragments_help')" placement="top">
                <el-input-number v-model="form.concurrent_fragments" :min="1" :max="20" />
              </el-tooltip>
            </el-form-item>
            <el-form-item :label="t('settings.generic_mode')">
              <el-tooltip :content="t('settings.generic_mode_help')" placement="top">
                <el-switch v-model="form.generic_mode" />
              </el-tooltip>
              <span class="help">{{ t('settings.enable_generic_mode') }}</span>
            </el-form-item>
            <el-form-item :label="t('web.notification_sounds')">
              <el-switch v-model="form.play_notification_sound" />
            </el-form-item>
            <el-form-item :label="t('language.select_language')">
              <el-select v-model="form.language" style="width: 160px">
                <el-option label="English" value="en" />
                <el-option label="中文" value="zh" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- ============ Format ============ -->
      <el-tab-pane :label="t('settings.output_format_settings')" name="format">
        <div class="yts-card">
          <el-form label-width="220px">
            <el-form-item :label="t('settings.force_output_format')">
              <el-tooltip :content="t('settings.force_format_help')" placement="top"><el-switch v-model="form.force_output_format" /></el-tooltip>
            </el-form-item>
            <el-form-item :label="t('settings.preferred_format')">
              <el-select v-model="form.preferred_output_format" style="width: 160px" :disabled="!form.force_output_format">
                <el-option :label="t('settings.format_mp4')" value="mp4" />
                <el-option :label="t('settings.format_webm')" value="webm" />
                <el-option :label="t('settings.format_mkv')" value="mkv" />
              </el-select>
            </el-form-item>

            <el-divider />
            <el-form-item :label="t('settings.force_audio_format')">
              <el-tooltip :content="t('settings.force_audio_format_help')" placement="top"><el-switch v-model="form.force_audio_format" /></el-tooltip>
            </el-form-item>
            <el-form-item :label="t('settings.preferred_audio_format')">
              <el-select v-model="form.preferred_audio_format" style="width: 160px" :disabled="!form.force_audio_format">
                <el-option v-for="f in audioFormats" :key="f" :label="t(`settings.audio_format_${f}`)" :value="f" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('settings.audio_normalization')">
              <el-tooltip :content="t('settings.audio_normalization_help')" placement="top">
                <el-switch v-model="form.audio_normalization" @change="onNormalization" />
              </el-tooltip>
            </el-form-item>

            <el-divider />
            <el-form-item :label="t('settings.defaults_settings')">
              <span class="help">{{ t('settings.defaults_help') }}</span>
            </el-form-item>
            <el-form-item :label="t('settings.default_video_quality')">
              <el-input v-model="form.default_video_quality" placeholder="1080" style="width: 160px" clearable />
            </el-form-item>
            <el-form-item :label="t('settings.default_subtitle_language')">
              <el-input v-model="form.default_subtitle_language" placeholder="en, es" style="width: 220px" clearable />
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- ============ File ============ -->
      <el-tab-pane :label="t('settings.tab_file')" name="file">
        <div class="yts-card">
          <el-form label-width="220px">
            <el-form-item :label="t('settings.filename_format')">
              <el-input v-model="form.filename_format" style="width: 480px" />
              <el-button style="margin-left: 8px" @click="form.filename_format = DEFAULT_FILENAME">{{ t('buttons.reset') }}</el-button>
            </el-form-item>
            <el-form-item>
              <span class="help">{{ t('settings.filename_format_help') }}</span>
            </el-form-item>
            <!-- Drag-and-drop block builder; keeps the input above in sync -->
            <el-form-item :label="t('web.filename.sequence')">
              <FilenameBuilder v-model="form.filename_format" />
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- ============ Security ============ -->
      <el-tab-pane :label="t('web.security')" name="security">
        <div class="yts-card">
          <el-form label-width="220px">
            <el-form-item :label="t('web.current_password')">
              <el-input v-model="pwd.current_password" type="password" show-password style="width: 280px" />
            </el-form-item>
            <el-form-item :label="t('web.new_password')">
              <el-input v-model="pwd.new_password" type="password" show-password style="width: 280px" />
            </el-form-item>
            <el-form-item :label="t('web.confirm_password')">
              <el-input v-model="pwd.confirm_password" type="password" show-password style="width: 280px" />
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="changingPwd" @click="changePwd">{{ t('web.change_password') }}</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="tab !== 'security'" style="margin-top: 8px">
      <el-button type="primary" :loading="saving" @click="save">{{ t('settings.save_settings') }}</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useSettingsStore } from '@/stores/settings'
import { changePassword } from '@/api/auth'
import { errText } from '@/api/http'
import FilenameBuilder from '@/components/FilenameBuilder.vue'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const DEFAULT_FILENAME = '%(title)s_%(resolution)s_[%(id)s].%(ext)s'
const audioFormats = ['best', 'aac', 'mp3', 'flac', 'wav', 'opus', 'm4a', 'vorbis']

const tab = ref('general')
const form = ref({})
const saving = ref(false)
const changingPwd = ref(false)
const pwd = ref({ current_password: '', new_password: '', confirm_password: '' })

// Official linkage: enabling normalization forces audio format + best->mp3;
// disabling force_output_format cancels normalization.
function onNormalization(val) {
  if (val) {
    form.value.force_audio_format = true
    if (form.value.preferred_audio_format === 'best') form.value.preferred_audio_format = 'mp3'
  }
}

async function save() {
  saving.value = true
  try {
    await settingsStore.save(form.value)
    ElMessage.success(t('settings.settings_saved_successfully'))
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    saving.value = false
  }
}

async function changePwd() {
  const p = pwd.value
  if (!p.current_password || !p.new_password) return ElMessage.warning(t('web.fill_all_fields'))
  if (p.new_password !== p.confirm_password) return ElMessage.error(t('web.passwords_mismatch'))
  if (p.new_password.length < 4) return ElMessage.error(t('web.password_too_short'))
  changingPwd.value = true
  try {
    await changePassword(p.current_password, p.new_password)
    ElMessage.success(t('web.password_changed'))
    pwd.value = { current_password: '', new_password: '', confirm_password: '' }
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    changingPwd.value = false
  }
}

onMounted(async () => {
  const s = await settingsStore.fetch(true)
  if (s) form.value = { ...s }
})
</script>

<style scoped>
.help { color: var(--yts-text-dim); font-size: 12px; margin-left: 12px; }
:deep(.el-tabs__item) { color: var(--yts-text-dim); }
:deep(.el-tabs__item.is-active) { color: var(--yts-red); }
:deep(.el-tabs__active-bar) { background-color: var(--yts-red); }
:deep(.el-divider__text) { background: var(--yts-panel); }
</style>
