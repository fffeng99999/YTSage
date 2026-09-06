/**
 * i18n setup: messages are fetched from the backend /api/i18n/{lang},
 * which serves the OFFICIAL ytsage/languages/{zh,en}.json files verbatim.
 * Frontend uses the same dotted keys as the desktop app (e.g.
 * t('main_ui.url_placeholder')), so upstream text changes sync for free.
 */
import { createI18n } from 'vue-i18n'
import axios from 'axios'

export const SUPPORTED_LANGS = ['en', 'zh']

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('ytsage_lang') || 'en',
  fallbackLocale: 'en',
  messages: {},
  // Official files use {name} named interpolation - compatible with vue-i18n
  missingWarn: false,
  fallbackWarn: false,
})

const loaded = new Set()

// Web-specific strings that don't exist in the official desktop language
// files (the desktop app has no Jobs page / security tab / etc.)
const WEB_EXTRA = {
  en: {
    web: {
      jobs: 'Download Jobs', security: 'Security', logout: 'Logout',
      confirm_logout: 'Are you sure you want to logout?',
      current_password: 'Current Password', new_password: 'New Password',
      confirm_password: 'Confirm Password', change_password: 'Change Password',
      password_changed: 'Password changed successfully',
      fill_all_fields: 'Please fill all fields',
      passwords_mismatch: 'Passwords do not match',
      password_too_short: 'Password too short (min 4 chars)',
      notification_sounds: 'Notification Sounds',
      recent_downloads: 'Recent Downloads',
      embed: 'Embed', chapters: 'Chapters', metadata: 'Metadata', thumbnail: 'Thumbnail',
      default_password_hint: 'Default password: ytsage',
      download_path_label: 'Download Path',
      login: 'Login', login_failed_invalid: 'Invalid password',
      cookie_content_label: 'Cookie Content',
      cookie_content_placeholder: 'Paste Netscape-format cookie text here (one entry per line):\n.example.com\tTRUE\t/\tTRUE\t1735689600\tcookie_name\tcookie_value',
      cookie_content_help: 'The text is saved to %APPDATA%/YTSage/cookies.txt on the server and also applies to the desktop app.',
      cookies_empty: 'Please paste cookie content first',
      cookies_invalid: 'Invalid Netscape cookie format (expect 7 tab-separated fields per line)',
      setup_title: 'Initial Setup',
      setup_step1: 'Language', setup_step2: 'Password', setup_step3: 'Configuration',
      setup_lang_desc: 'Choose the Web UI language.',
      setup_pwd_desc: 'Set the Web UI login password (at least 4 characters).',
      setup_mode_desc: 'Where should the Web UI store its settings?',
      setup_mode_standalone: 'Standalone (recommended)',
      setup_mode_standalone_help: 'Settings are stored in the Web UI\'s own directory. The desktop app config directory is never read or written.',
      setup_mode_shared: 'Shared with desktop app',
      setup_mode_shared_help: 'Use the official YTSage config so desktop app and Web UI stay in sync.',
      setup_import: 'Import current desktop app settings as starting values',
      setup_next: 'Next', setup_back: 'Back', setup_finish: 'Finish Setup',
    },
  },
  zh: {
    web: {
      jobs: '下载任务', security: '安全', logout: '退出登录',
      confirm_logout: '确定要退出登录吗?',
      current_password: '当前密码', new_password: '新密码',
      confirm_password: '确认新密码', change_password: '修改密码',
      password_changed: '密码修改成功',
      fill_all_fields: '请填写所有字段',
      passwords_mismatch: '两次输入的密码不一致',
      password_too_short: '密码太短(至少 4 位)',
      notification_sounds: '通知声音',
      recent_downloads: '最近下载',
      embed: '嵌入选项', chapters: '章节', metadata: '元数据', thumbnail: '封面',
      default_password_hint: '默认密码: ytsage',
      download_path_label: '下载路径',
      login: '登录', login_failed_invalid: '密码错误',
      cookie_content_label: 'Cookie 内容',
      cookie_content_placeholder: '在此粘贴 Netscape 格式的 Cookie 文本(每行一条):\n.example.com\tTRUE\t/\tTRUE\t1735689600\tcookie_name\tcookie_value',
      cookie_content_help: '内容将保存到服务器 %APPDATA%/YTSage/cookies.txt,桌面版也可同步使用。',
      cookies_empty: '请先粘贴 Cookie 内容',
      cookies_invalid: 'Netscape Cookie 格式无效(每行应为 7 个制表符分隔字段)',
      setup_title: '初始化设置',
      setup_step1: '语言', setup_step2: '密码', setup_step3: '配置',
      setup_lang_desc: '选择 Web UI 界面语言。',
      setup_pwd_desc: '设置 Web UI 登录密码(至少 4 位)。',
      setup_mode_desc: 'Web UI 的设置保存在哪里?',
      setup_mode_standalone: '独立存储(推荐)',
      setup_mode_standalone_help: '设置保存在 Web UI 自己的目录,不会读写桌面版的配置目录(Linux 上尤其重要)。',
      setup_mode_shared: '与桌面版共享',
      setup_mode_shared_help: '使用官方 YTSage 配置,桌面版与 Web UI 设置实时同步。',
      setup_import: '导入桌面版当前设置作为初始值',
      setup_next: '下一步', setup_back: '上一步', setup_finish: '完成设置',
    },
  },
}

export async function loadLocale(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en'
  if (loaded.has(lang)) {
    i18n.global.locale.value = lang
    localStorage.setItem('ytsage_lang', lang)
    return
  }
  try {
    const { data } = await axios.get(`/api/i18n/${lang}`, { timeout: 15000 })
    i18n.global.setLocaleMessage(lang, { ...data, ...(WEB_EXTRA[lang] || {}) })
    loaded.add(lang)
    i18n.global.locale.value = lang
    localStorage.setItem('ytsage_lang', lang)
  } catch (e) {
    console.error('loadLocale failed:', e)
    if (lang !== 'en') await loadLocale('en')
  }
}

export default i18n
