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
      batch_title: 'Batch & Channel',
      clipboard_manual_paste: 'Direct clipboard access is unavailable (page not opened via https/localhost). Paste the link here with Ctrl+V:',
      clipboard_manual_placeholder: 'Paste here (Ctrl+V)…',
      ffmpeg: {
        update_button: 'Update FFmpeg',
        update_success: 'FFmpeg updated successfully',
      },
      rollback: {
        button: 'Roll Back',
        to: 'Roll back to {version}',
        confirm_title: 'Roll back version',
        confirm_message: 'Restore the previously installed version {version}? This replaces the current installation with the copy archived on this machine.',
        busy: 'Rolling back…',
        success: 'Rolled back to {version}',
        failed: 'Rollback failed: {error}',
        no_history: 'No previous installed version is archived for this component yet. A rollback becomes available after the first update performed here.',
        hint: 'Rolls back to the previous version installed on this machine (not the previous upstream release).',
      },
      errors: {
        postprocessing_failed: "The download finished but post-processing failed (merging / subtitle embedding / SponsorBlock chapter editing). The link is fine - try again with SponsorBlock or 'merge subtitles' turned off, or pick a different quality. Details: {error}",
      },
      codec: {
        title: 'Video Codec Priority',
        help: 'Drag to order. Batch & channel downloads prefer the top codec and only fall back to lower ones when it is unavailable. Codecs left in the pool are used as a last resort.',
        pool: 'Unused Codecs',
        pool_empty: 'All codecs are in the priority list',
        sequence: 'Priority Order (drag to reorder)',
        empty: 'Drag codecs here to set priority',
        hint_pool: 'Drag a codec into the priority list; drag it back here to deprioritize it.',
        hint_seq: 'Top = highest priority. Click × to remove a codec from the list.',
      },
      filename: {
        pool: 'Block Pool (unused tokens)',
        sequence: 'Filename Sequence (drag to reorder)',
        text: 'Text',
        empty: 'Drag blocks here to build the filename',
        hint_pool: 'Drag a block into the sequence on the right. Drop a block back here to remove it.',
        hint_seq: 'Order here = order in the filename. Double-click a blue text block to edit it.',
        tokens: {
          title: 'Title', uploader: 'Uploader', upload_date: 'Upload Date',
          resolution: 'Resolution', id: 'Video ID', ext: 'Extension',
        },
      },
      presets: {
        best: 'Best Available', '2160': '2160p (4K)', '1440': '1440p (2K)',
        '1080': '1080p (Full HD)', '720': '720p (HD)', '480': '480p',
        '360': '360p', '240': '240p', '144': '144p', worst: 'Lowest Available',
      },
      presetsRes: {
        best: 'Max Quality', '2160': '≤ 3840x2160', '1440': '≤ 2560x1440',
        '1080': '≤ 1920x1080', '720': '≤ 1280x720', '480': '≤ 854x480',
        '360': '≤ 640x360', '240': '≤ 426x240', '144': '≤ 256x144', worst: 'Worst Available',
      },
      concurrent_downloads: 'Simultaneous Downloads',
      concurrent_downloads_help: 'How many download tasks may run at the same time across all pages (single, batch and channel). Extra tasks wait in a queue until a slot frees up. Default: 1.',
      channel_err: {
        watch_url: "This is a video URL. Please paste the channel homepage URL (e.g. youtube.com/{'@'}handle).",
        playlist_url: 'This is a playlist URL. Use the single-download page instead.',
        invalid_channel_url: "Not a valid channel URL (expected {'@'}handle, /channel/..., /c/... or /user/...).",
        invalid_tab: 'Invalid channel tab.',
        empty_channel: 'No videos found in this channel tab.',
        not_a_channel: 'The URL did not resolve to a channel/playlist.',
      },
      batch: {
        tab: 'Batch Download',
        placeholder: 'Paste video/playlist URLs, one per line (max 50)',
        hint: 'One URL per line, up to {max} URLs',
        parse: 'Parse All',
        too_many: 'Too many URLs (max {max})',
        col_video: 'Video',
        col_codec: 'Codec',
        col_status: 'Status',
        parsed_ok: 'Parsed',
        queued: 'Queued',
        failed: 'Failed',
        playlist_count: 'Playlist · {count} videos',
        concurrency: 'Concurrency',
        audio_only: 'Audio Only',
        quality: 'Quality',
        q_auto: 'Auto (best)',
        q_default: '(default)',
        defaults_hint: 'Download path and quality default to the global Settings (download path, default video quality, default subtitle language).',
        need_path: 'Please set a download path first',
        download_selected: 'Download Selected ({count})',
        progress: '{done} / {total} finished',
        done_title: 'Downloads finished',
        done_message: '{count} download job(s) completed',
        go_to_jobs: 'View Jobs',
      },
      channel: {
        tab: 'Channel Download',
        url_placeholder: "Channel homepage URL, e.g. https://www.youtube.com/{'@'}handle",
        tab_videos: 'Videos', tab_shorts: 'Shorts', tab_streams: 'Streams',
        page_size: 'Per page',
        total: '{count} videos in channel',
        loaded: '{count} videos loaded',
        selected: '{count} selected',
        search_placeholder: 'Search video titles…',
        col_pos: 'No.',
        selected_tag: 'Selected',
        pinned_note: '(pinned)',
        next_page: 'Load next page →',
        empty: 'No videos found',
        select_all: 'Select All / None',
      },
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
      batch_title: '批量下载',
      clipboard_manual_paste: '无法直接读取剪贴板(页面未通过 https/localhost 打开)。请在此按 Ctrl+V 粘贴链接:',
      clipboard_manual_placeholder: '在此粘贴(Ctrl+V)…',
      ffmpeg: {
        update_button: '更新 FFmpeg',
        update_success: 'FFmpeg 更新成功',
      },
      rollback: {
        button: '回退版本',
        to: '回退到 {version}',
        confirm_title: '版本回退',
        confirm_message: '确定恢复到上一个安装的版本 {version} 吗？将用本机归档的旧版本覆盖当前安装。',
        busy: '正在回退…',
        success: '已回退到 {version}',
        failed: '回退失败：{error}',
        no_history: '该组件还没有已归档的上一个安装版本。在本页面完成第一次更新后即可回退。',
        hint: '回退到本机上一个安装的版本（不是上游的上一个发布版本）。',
      },
      errors: {
        postprocessing_failed: "视频已下载完成，但后处理失败（合并、内嵌字幕或 SponsorBlock 章节编辑）。链接本身没有问题——请尝试关闭 SponsorBlock 或“合并字幕”后重试，或换一种画质。详情：{error}",
      },
      codec: {
        title: '视频编码优先级',
        help: '拖拽排序。批量下载与频道下载优先选择排在上方的编码，仅在其不可用时才回退到后面的编码；留在块池中的编码只作为最后兜底使用。',
        pool: '未使用的编码',
        pool_empty: '所有编码都已在优先级列表中',
        sequence: '优先级顺序（拖拽排序）',
        empty: '把编码拖到这里设置优先级',
        hint_pool: '把编码拖入右侧优先级列表；拖回这里即降低为兜底。',
        hint_seq: '越靠前优先级越高；点击 × 移出列表。',
      },
      filename: {
        pool: '块池（未使用的通配符）',
        sequence: '文件名顺序（拖拽排序）',
        text: '文本',
        empty: '把块拖到这里组合文件名',
        hint_pool: '把块拖到右侧序列中；拖回这里即移除。',
        hint_seq: '这里的顺序就是文件名的顺序；双击蓝色文本块可编辑内容。',
        tokens: {
          title: '标题', uploader: '上传者', upload_date: '上传日期',
          resolution: '分辨率', id: '视频ID', ext: '扩展名',
        },
      },
      presets: {
        best: '最佳画质', '2160': '2160p (4K)', '1440': '1440p (2K)',
        '1080': '1080p (全高清)', '720': '720p (高清)', '480': '480p',
        '360': '360p', '240': '240p', '144': '144p', worst: '最低画质',
      },
      presetsRes: {
        best: '最高画质', '2160': '≤ 3840x2160', '1440': '≤ 2560x1440',
        '1080': '≤ 1920x1080', '720': '≤ 1280x720', '480': '≤ 854x480',
        '360': '≤ 640x360', '240': '≤ 426x240', '144': '≤ 256x144', worst: '最低画质',
      },
      concurrent_downloads: '并发下载数',
      concurrent_downloads_help: '所有页面（单个、批量、频道下载）允许同时进行的下载任务数量，超出的任务自动排队等待空闲名额。默认值：1。',
      channel_err: {
        watch_url: "这是视频链接,请粘贴博主主页链接(例如 youtube.com/{'@'}handle)。",
        playlist_url: '这是播放列表链接,请使用单链接下载页面。',
        invalid_channel_url: "不是有效的频道链接(应为 {'@'}handle、/channel/...、/c/... 或 /user/...)。",
        invalid_tab: '频道页签无效。',
        empty_channel: '该频道页签下没有找到视频。',
        not_a_channel: '链接未能解析为频道/播放列表。',
      },
      batch: {
        tab: '批量下载',
        placeholder: '粘贴视频/播放列表链接,每行一个(最多 50 个)',
        hint: '每行一个链接,最多 {max} 个',
        parse: '解析全部',
        too_many: '链接过多(最多 {max} 个)',
        col_video: '视频',
        col_codec: '编码',
        col_status: '状态',
        parsed_ok: '已解析',
        queued: '排队中',
        failed: '失败',
        playlist_count: '播放列表 · {count} 个视频',
        concurrency: '并发数',
        audio_only: '仅音频',
        quality: '画质',
        q_auto: '自动(最高)',
        q_default: '(默认)',
        defaults_hint: '下载路径与画质默认取自全局设置(下载目录、默认视频画质、默认字幕语言)。',
        need_path: '请先设置下载目录',
        download_selected: '下载选中({count})',
        sponsorblock_tip: '去除赞助片段；与字幕同时使用时，部分视频可能触发 yt-dlp 已知后处理错误（Result too large），请谨慎使用。',
        options_hint: '以上选项对所有选中视频生效；没有字幕/缩略图/描述的视频会自动跳过对应部分，不影响下载。',
        progress: '已完成 {done} / {total}',
        done_title: '下载已结束',
        done_message: '共完成 {count} 个下载任务',
        go_to_jobs: '查看任务',
      },
      channel: {
        tab: '频道下载',
        url_placeholder: "博主主页链接,例如 https://www.youtube.com/{'@'}handle",
        tab_videos: '视频', tab_shorts: 'Shorts', tab_streams: '直播',
        page_size: '每页条数',
        total: '频道共 {count} 个视频',
        loaded: '已加载 {count} 个视频',
        selected: '已选 {count} 个',
        search_placeholder: '搜索视频标题…',
        col_pos: '序号',
        selected_tag: '已选',
        pinned_note: '(置顶)',
        next_page: '加载下一页 →',
        empty: '未找到视频',
        select_all: '全选 / 全不选',
      },
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
