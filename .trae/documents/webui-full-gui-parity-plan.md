# YTSage Web UI 完整复刻官方 GUI — 实施方案

## Context

官方桌面 GUI(PySide6,`ytsage/`)功能完整,但需要 Web 控制界面以便浏览器远程下载。现有 `webui/`(FastAPI + Vue3)只覆盖约 30-40% 能力:缺字幕选择、SponsorBlock 类别、播放列表条目选择、Cookies、限速、片段裁剪、音频转换、多音轨合并、历史记录、更新器、自定义命令、i18n;且存在假暂停、删除任务不杀进程、WS 无鉴权等缺陷。

**硬性约束**:禁止修改 `ytsage/` 官方源码(保证 git pull 零冲突);所有代码只放 `webui/`、`run_webui.py`、`.gitignore`。

**用户决策**:① 布局按 Web 通用标准拆分(侧边栏多页面),但功能 100% 覆盖官方 GUI;② 更新器全套复刻(yt-dlp stable/nightly+自动更新、ffmpeg 检查+安装、Deno 检查+更新、应用本体检查);③ i18n 仅中/英,复用官方 `ytsage/languages/{zh,en}.json`(34 个命名空间,`{count}` 占位符与 vue-i18n 兼容);④ 保留多任务并发;⑤ 界面贴近官方深色红主题(`#15181b`/`#1b2021`/`#c90000`)。

**已实测**:`.venv`(Py3.12)中 `ytsage.utils.*`(ConfigManager/HistoryManager/Localization/constants)全部可导入;`ytsage.core.*` 因 PySide6 不可导入 → 核心逻辑(更新器、URL 校验、错误解析)移植进 webui,逐函数注释"对标 官方文件:行号"。

---

## 一、后端(webui/)

### 新增模块

| 文件 | 职责 |
|---|---|
| `official_bridge.py` | 集中 try/except 导入官方模块,导出能力标志(HAS_CONFIG/HAS_HISTORY/HAS_FFMPEG_CORE);ConfigManager/HistoryManager 一律 `asyncio.to_thread()` 包装 |
| `schemas.py` | 全部 Pydantic 模型;DownloadRequest 扩展 `save_thumbnail/title/channel/duration/thumbnail_url/analysis_id`;SettingsUpdate 逐键类型/范围校验 |
| `settings_service.py` | 33 键完整白名单(补 `speed_limit_unit_index, cookie_browser_profile, cookie_active, cookie_remember, play_notification_sound, default_video_quality, default_subtitle_language, auto_update_ytdlp, auto_update_frequency, last_update_check, check_app_updates, check_beta_updates, ytdlp_channel`);`build_download_defaults()` 统一注入 proxy/geo/限速换算字节/cookie(仅 cookie_active 时)/filename_format/并发/格式强制项 — 对标官方 `ytsage_downloader.py` L879-891、`ytsage_gui_main.py` L252-253/L355-380 |
| `event_bus.py` | 从 DownloadManager 抽出 WS 广播总线;每 job 100ms 节流;队列 maxsize=1000 满则丢中间态保终态 |
| `history_service.py` | HistoryManager 异步门面:list/search/get/delete/clear/add;`download_options` 字典键与官方 `ytsage_gui_main.py` L1013-1025 完全一致(桌面版可互通共库);`database is locked` 退避重试 3 次 |
| `thumbnail_service.py` | `GET /api/thumbnail?url=` 代理(https 白名单+`APP_THUMBNAILS_DIR/<sha1>.jpg` 缓存);save_thumbnail 落盘 `<path>/Thumbnails/<sanitize(title)>.jpg`(sanitize 正则照抄官方 L471-472) |
| `playlist_export.py` | txt/m3u/csv/json 四种导出,逐字段对标官方 `save_playlist_to_file`(L1650-1720),StreamingResponse 附件 |
| `command_service.py` | 自定义命令:`create_subprocess_exec` 流式读行→WS `command_output`;exec_id 注册表+取消(杀进程树) |
| `updater_service.py` | 移植官方更新逻辑:yt-dlp 检查/更新/`--update-to stable|nightly` 频道切换(失败回滚)/自动更新调度(startup=1h 去重、daily、weekly,对标 `should_check_for_auto_update`);ffmpeg 检查+安装(优先复用 `ytsage.core.ytsage_ffmpeg`,补装 requests);Deno 检查+`deno upgrade`;应用本体 PyPI+GitHub changelog+beta 开关;全局 `updating_ytdlp` 标志双向互斥(更新中 analyze/download 409,有活动 job 时更新 409) |
| `system_service.py` | `/api/system/status`(三件套版本/路径/Deno 集成检测)、reveal/open-folder(`explorer /select,`;路径前缀白名单=download_path+APP 目录)、open-logs、通知音 FileResponse |
| `url_utils.py` | `validate_video_url`(generic_mode 双策略)+ `parse_yt_dlp_error`(12 类友好文案)移植 |

### 存量改造

- **`download_manager.py`**:
  - 真暂停:进程继续跑,读循环 `while paused: await sleep(0.1)`(对标官方 L556-557 协作式)
  - 取消/删除:Windows `taskkill /F /T /PID`、Unix `killpg`(对标官方 `_terminate_process_tree` L160-192)+ sleep 2s + 清理 `.part`/`.f\d+.`(移植 `cleanup_partial_files` L125);merge_subs 完成后清理独立字幕文件
  - 进度正则加固:兼容无小数 `(\d+(\.\d+)?)%`、`N/A` 速度、小时级 ETA;阶段映射 Destination→0/Merger→95/SponsorBlock→97/Deleting original→98/Finished→100;`has already been downloaded` → `file_exists` 事件
  - job 元数据 + 完成后写历史(payload 附 `history_id/file_path/file_size/file_kind`)
- **`analysis_service.py`**:结果缓存 `analysis_id→result`(TTL 1h,LRU 20);规范化 `subtitles:[{code,type,ext}]`;裁剪 formats 大字段;默认注入 cookie/proxy
- **`server.py`**:WS 强制 token(无→close 1008);CORS 收敛为 dev 白名单;catch-all 对 `/api/*` 返回 JSON 404;settings 换 33 键+校验;analyze/download 走 `build_download_defaults()`;新增全部端点(见下)
- **`run_webui.py`**:启动钩子触发自动更新调度
- **`webui/requirements.txt`**:追加 `requests>=2.32.5`、`packaging>=25.0`(官方 pyproject 已有依赖,使 ytsage_ffmpeg 可直接复用)

### 新增 API 端点

```
GET    /api/history?q=            GET /api/history/{id}
DELETE /api/history/{id}          DELETE /api/history
GET    /api/thumbnail?url=        GET  /api/sound/notification
POST   /api/playlist/export       GET  /api/analysis/{analysis_id}
POST   /api/system/reveal         POST /api/system/open-folder
POST   /api/system/open-logs      GET  /api/system/status
POST   /api/cookies/apply         POST /api/cookies/clear       GET /api/cookies/status
POST   /api/command/run           POST /api/command/{id}/cancel
GET    /api/updater/state
POST   /api/updater/ytdlp/check | update | channel | auto
POST   /api/updater/ffmpeg/check | install
POST   /api/updater/deno/check | update
POST   /api/updater/app/check
GET    /api/i18n/{lang}           (zh|en,读官方 languages/*.json 并缓存)
```

WS 事件扩展:`job_*`(现有)+ `command_output/command_finished` + `updater{component,state,progress,message}`。

---

## 二、前端(webui/client/src/)

### 路由/页面(Layout 侧边栏 7 项)

| 页面 | 对标官方 | 内容 |
|---|---|---|
| Dashboard 工作台 | 主窗口全流程 | URL(粘贴/回车/generic_mode placeholder+校验)→ AnalysisProgress 阶段文案 → VideoInfoCard(缩略图/标题/频道/播放量/点赞/日期/时长;playlist 条目数)→ FormatTable → 选项行 → 下载 → 进度(0.01%、速度/ETA、阶段)→ 完成(通知音+📁打开文件夹定位) |
| Jobs | 下载控制区 | 全部任务、暂停/恢复/取消/删除、进度明细、打开文件夹 |
| History [新] | HistoryDialog | 卡片列表(缩略图/标题/频道/日期/大小/Audio|Video 徽章)、搜索、打开位置、重新下载(回填 URL+自动分析)、删除、清空 |
| Settings [改] | DownloadSettingsDialog 3 页 | General(路径/限速值+KB/s|MB/s/并发 1-20/generic_mode/通知音)、Format(强制+首选容器、强制+首选音频 8 项、归一化联动、default_video_quality、default_subtitle_language)、File(模板+重置)、安全(改密码) |
| Tools [新] | CustomOptionsDialog | Cookies 页(浏览器 8 项+Profile/文件+记住+Apply+激活徽标)、Custom Command 页(流式控制台)、Proxy 页(主/Geo scheme 校验+清除) |
| Updater [新] | UpdaterTabWidget+更新对话框 | yt-dlp(检查/更新/频道/自动更新+频率+上次检查)、FFmpeg(检查/安装+进度)、Deno(检查/更新)、应用(检查+changelog 渲染+beta 开关) |
| About [新] | AboutDialog | 版本、三件套状态/路径、打开日志目录 |

### 组件(components/)

`FormatTable`(单视频 10 列;视频行单选 radio、音频行 checkbox 多选→`--audio-multistreams`;Quality/FPS≥60 绿≥30 橙/HDR 青/5.1ch 环绕标注;`default_video_quality` 预选;**修复 Video tab 误滤 acodec=none**——只要求 `vcodec!=none`;playlist 模式切 6 列硬编码预设表 Best/2160p…/Lowest,format_id 表达式照抄官方 L349-360)、`SubtitleDialog`(Manual+Auto 合并、过滤、`default_subtitle_language` 预选、计数徽标、merge_subs)、`SponsorBlockDialog`(8 类;sponsor/selfpromo/interaction 默认勾)、`PlaylistDialog`(逐条勾选→"1-3,5" 串,官方 `_condense_indices` 算法)、`TimeRangeDialog`(HH:MM:SS 起止+force_keyframes)、`EmbedOptionsPanel`(chapters/metadata/thumbnail/save_thumbnail/save_description)、`AnalysisProgress`、`CommandConsole`、`VideoInfoCard`。

### 基础设施

- `styles/theme.css`:Element Plus CSS 变量覆盖为官方深色红主题
- `i18n/`:vue-i18n@^9;`scripts/sync-i18n.mjs`(`npm run i18n:sync`)从官方 zh/en.json 原样抽取到 `i18n/locales/`,前端直接复用官方 key;语言切换写 ConfigManager `language`(桌面版互通)
- `stores/`:`analysis.js`(分析结果+格式/字幕/SB/playlist/裁剪选择状态)、`settings.js`(缓存+generic_mode)、`updater.js`(状态机);`download.js` 扩展事件分发+完成通知音
- `composables/`:`useSound`(notification.mp3)、`useReveal`、`useWSEvents`
- api/ 新增 `history.js/updater.js/system.js/command.js/playlist.js`

---

## 三、实施阶段(每阶段独立验证)

- **阶段 0 后端地基**:official_bridge/schemas/settings_service/event_bus + download_manager 修复(真暂停/杀进程树/partial 清理/进度加固)+ server 安全修复。验证:登录取 token;无 token WS→1008;`GET /api/settings` 33 键;`concurrent_fragments:99`→400;`/api/nonexistent`→JSON 404;下载中 DELETE job→`tasklist` 无 yt-dlp/ffmpeg 残留、无 `.part`
- **阶段 1 后端全参数+历史+缩略图+导出+system**:验证:真实 URL analyze 返回 analysis_id+subtitles;download 带字幕/SB 类别/`download_section=*00:01:00-00:02:00`/save_thumbnail,完成后 `/api/history` 有记录且 options 键齐全、Thumbnails/ 有 jpg、playlist export m3u 头 `#EXTM3U`、`/api/thumbnail` 返回 image/jpeg
- **阶段 2 前端工作台**:Dashboard 重构+全部对话框组件+FormatTable+主题。验证:`npm run build`;浏览器实测 Video tab 出现 acodec=none 最高清行、多音频勾选→命令含 `--audio-multistreams`、小时级 ETA、完成弹通知+响铃、打开文件夹定位
- **阶段 3 历史页**:搜索/重新下载回填自动分析/删除/清空;官方桌面版打开同库可见 Web 写入记录(互通)
- **阶段 4 工具页**:cookies apply 后下载带 `--cookies-from-browser` 且不再注入 extractor-args;`/api/command/run --version` WS 收到输出+exit_code=0
- **阶段 5 更新器+关于**:ytdlp check 返回当前 vs PyPI;有任务时 update→409;nightly 切换后 `--version` 带后缀;ffmpeg/deno/app 检查正常;About 与 `%LOCALAPPDATA%\YTSage\bin` 一致
- **阶段 6 i18n+回归**:`npm run i18n:sync`;切中文全站文案变化且 `language=zh` 写入官方配置;对照官方 12 项功能清单逐项手工核对

## 四、风险与对策

| 风险 | 对策 |
|---|---|
| 桌面版与 Web 并发写同一 SQLite | 全部 to_thread 串行 + locked 退避重试;文档提示勿双开 |
| yt-dlp 更新与运行任务互锁(Windows 文件占用) | `updating_ytdlp` 双向互斥 409 |
| ffmpeg 同步安装阻塞事件循环 | to_thread + `call_soon_threadsafe` 投递进度 |
| 分析缓存内存大 | TTL 1h + LRU 20;过期提示重新分析 |
| 官方 git pull 漂移 | 移植点全部带"对标 文件:行号"注释;i18n 脚本重抽;升级后 diff `ytsage_downloader.py` |
| reveal/open-folder 路径探测 | token 必过 + 路径前缀白名单 |

## 五、关键对标文件(只读)

- `ytsage/core/ytsage_downloader.py` — 命令构建(L241-484)、进度解析(L667-886)、暂停/取消/清理(L125-192, L546-556)
- `ytsage/gui/ytsage_gui_main.py` — 配置注入、历史写入(L1013-1042)、更新调度、打开文件夹
- `ytsage/gui/ytsage_gui_format_table.py` — 格式表列/颜色/预设(L349-360)
- `ytsage/utils/ytsage_history_manager.py` — SQLite schema(直接复用)
- `ytsage/languages/{zh,en}.json` — i18n 源
