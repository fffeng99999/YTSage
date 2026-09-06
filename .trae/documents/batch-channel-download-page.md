# 新增「批量/频道下载」页面（导航栏第 2 位）

## Context（背景）

YTSage WebUI 目前只支持单链接解析下载（Dashboard）。参考 YoutubeDownloader（Tyrrrz）的功能，需要新增：

1. **多链接批量下载**：一次粘贴多个 URL，逐个解析后勾选下载。
2. **博主主页（频道）解析下载**：解析频道 URL（@handle / channel/UC… / c… / user…），按 videos/shorts/streams 分页签列出视频，勾选后选择性下载。

**硬性约束**：全部功能放在一个**新页面**，导航栏**第 2 个位置**（Dashboard 之后、任务之前）；**不删除、不修改任何现有功能**（现有文件只做"新增式"改动）。

## 总体设计

新页面 `Batch.vue` 用 `el-tabs` 分两个标签页；下载全部复用现有 `POST /api/download` + WebSocket 任务体系（Jobs 页可见进度），不新增下载逻辑。

- 批量下载：每个 URL 解析后，**每个链接独立创建一个下载任务**，前端按并发数（1/2/3/5）排队启动。
- 频道下载：解析用 `yt-dlp --flat-playlist --playlist-end N`；下载**复用现有播放列表路径**——向 `/api/download` 发 `is_playlist=true` + `playlist_items="1,3-5"`（频道 URL 归一化为 `.../videos` 等页签），后端 `build_ytdlp_command` 已完整支持，零改动。

## 后端改动

### 1. 新文件 `webui/channel_service.py`

复用 `analysis_service.py` 的 `_sync_run`、`build_auth_options`、`cache_put`、`analyze_url_async`：

- `normalize_channel_url(url, tab)`：校验 YouTube 域名（复用 `url_utils.YOUTUBE_DOMAINS`）；拒绝 watch/playlist URL（返回 i18n 错误 key）；接受 `@handle`、`/channel/`、`/c/`、`/user/`，剥离尾部页签和 query，追加 `/{tab}`（videos|shorts|streams）。
- `analyze_channel(url, tab, limit, cookie_file, browser_cookies, proxy_url, geo_proxy_url)`：
  - 命令：`[yt-dlp, --dump-single-json, --flat-playlist, --no-warnings, --playlist-end, limit, norm_url]`
  - 返回 `{channel_info: {title, id, uploader, normalized_url, tab}, entries: [{index(数组位 i+1), id, title, url, duration, thumbnail}], total, analysis_id}`
  - 缩略图：flat 条目常无顶层 `thumbnail`，从 `thumbnails[0].url` 取，否则构造 `https://i.ytimg.com/vi/{id}/hqdefault.jpg`（i.ytimg.com 在缩略图代理白名单内；**不使用 yt3.ggpht.com 频道头像**）。
  - 结果 `cache_put` 进缓存（免费获得 `GET /api/analysis/{id}`）。
- `analyze_batch(urls, ...)`：`asyncio.Semaphore(3)` + `asyncio.gather` 调 `analyze_url_async`；每个 URL 先 `validate_video_url`，失败行返回 `{url, ok:false, error, error_key}`（用 `parse_yt_dlp_error_key`）；成功行返回精简摘要 `{url, ok:true, is_playlist, analysis_id, summary:{title, channel, thumbnail, duration_string, count}}`，**不返回 all_formats**（减小响应体）。上限 50 个 URL。

### 2. `webui/schemas.py`（纯新增）

- `BatchAnalyzeRequest { urls: List[str], cookie_file?, browser_cookies?, proxy_url?, geo_proxy_url? }`
- `ChannelAnalyzeRequest { url, tab: pattern(videos|shorts|streams), limit: 1..1000, + cookie/proxy 字段 }`

### 3. `webui/server.py`（在 `/api/analyze` 附近新增两条路由，模式照抄现有 `analyze()`：`Depends(get_current_user)` + `_ensure_not_updating()` + defaults 注入 + RuntimeError→400）

- `POST /api/analyze/batch` → `{results: [...]}`
- `POST /api/analyze/channel` → analyze_channel 结果

### 4. `webui/download_manager.py` — **不改**

音频批量下载在前端发 `format_id: 'bestaudio', is_audio_only: true`，走现有单视频分支 L205-206，行为正确。

## 前端改动

### 5. 新文件 `webui/client/src/api/batch.js`

`analyzeBatch` / `analyzeChannel`，per-request `timeout: 300000`（http.js 默认 30s 不够）。

### 6. `webui/client/src/router/index.js`

children 数组 Dashboard 之后插入 `{ path: 'batch', name: 'Batch', component: () => import('@/views/Batch.vue') }`。

### 7. `webui/client/src/views/Layout.vue`

- `/jobs` 之前插入 `<el-menu-item index="/batch">`（图标 `CopyDocument`，文案 `t('web.batch_title')`）。
- `pageTitle` switch 新增 `case '/batch'`。

### 8. `webui/client/src/i18n/index.js`

WEB_EXTRA 的 en/zh 两块 `web` 下新增 `batch_title` 及 `batch.*`、`channel.*` 文案组。

### 9. 新文件 `webui/client/src/views/Batch.vue`（核心页面）

**批量下载 tab**：
- 多行文本框（每行一个 URL）+ 粘贴按钮 + 解析按钮；前端去重、上限 50。
- 结果 `el-table`（selection 列 + 缩略图 `/api/thumbnail?url=` + 标题/频道/时长/状态列；解析失败行显示 `t(error_key)`）。
- 画质下拉复用 `PLAYLIST_PRESETS`（从 `@/stores/analysis` 导入）+ "仅音频"；下载路径（默认 `settingsStore.downloadPath`）；并发数 1/2/3/5。
- "下载选中"：每个选中行 POST `/api/download`（视频行：`format_id` = preset；音频行：`is_audio_only:true, format_id:'bestaudio'`；播放列表行：`is_playlist:true` 整体下载并提示"含 N 个视频"）。
- 排队泵：`watch` `downloadStore.jobs`（**不用 `onFinished`，它有监听器泄漏问题**），跟踪 `Map<job_id, row>`，任务到达终态（completed/error/cancelled）后启动队列中下一个；全部结束弹通知 + 跳转 Jobs 链接。

**频道下载 tab**：
- URL 输入 + 页签单选（视频/Shorts/直播）+ 数量上限（50/100/200/500）+ 解析。
- 显示频道标题/视频总数；`el-table` 勾选列表（同样缩略图模式，`max-height` 滚动）。
- "下载选中"：**单个任务**——`playlist_items` = 选中行的数组位压缩串（`condenseIndices` 从 analysis.js 复制为组件内工具函数，不改动 store），全选时传 null；`url` 用后端返回的 `normalized_url`；`is_playlist: true`；画质走 preset（音频 preset 时 `is_audio_only:true, format_id:null`，播放列表分支 L183 已处理）。
- 下载后同样 watch 该 job 显示进度。

## 实施顺序

后端（channel_service → schemas → server 路由）→ 前端（api → Batch.vue → router → Layout → i18n）→ `npm run build` → 重启后端。

## 验证

1. `cd webui/client && npm run build` 无报错；重启 `.venv\Scripts\python run_webui.py`，`GET /api/health` ok。
2. 导航栏第 2 项为"批量下载"，中英切换正常；原 7 个页面全部可用。
3. 回归：Dashboard 单视频/播放列表下载、History 重新下载不受影响（download_manager 未动）。
4. 频道接口：`@handle` URL + tab=videos + limit=5 → 返回 5 条含 url/thumbnail/normalized_url；粘贴 watch URL → 400 带错误 key。
5. 批量接口：2 个有效 + 1 个无效 URL → 混合结果，无效行显示翻译后错误。
6. 频道勾选非连续行下载 → 请求 payload `playlist_items` 形如 `"2,4-6"`，文件落在 `<路径>/<频道页签标题>/` 下；Jobs 页可见进度。
7. 批量 3 个 URL 并发 1 → 任务依次启动；音频行服务端日志出现 `-f bestaudio`。
