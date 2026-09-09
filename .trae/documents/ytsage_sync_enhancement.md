# YTSage Sync 功能增强计划 - 复刻 dysync.net 全部功能

## Context

用户要求仿照 dysync.net（抖音同步工具）实现类似的 YouTube 同步功能。当前 YTSage 已有基础 sync 模块（`webui/sync/`），包含 profiles、targets、records、schedules、settings 五个子页面。经对比分析，现有实现覆盖了 dysync 约 40% 的功能，需要增强以下缺失功能：

1. **数据看板** - 统计卡片 + 7天趋势图 + 作者排行
2. **视频在线播放** - HTTP Range 流式播放
3. **订阅频道管理** - 独立页面，按频道粒度管理同步状态
4. **Cookie 管理** - 有效性检测、过期提醒
5. **记录增强** - 批量操作、过滤器、软删除/恢复、分享链接
6. **NFO 刮削** - Emby/Jellyfin 兼容元数据文件
7. **系统日志页** - 独立日志查看（从 About 中独立出来）

## 菜单结构（修改后）

```
下载 / 批量 / 任务 / 历史 / 设置 / 工具 / 更新
├── YT 同步 (el-sub-menu)
│   ├── 数据看板        ← 新增
│   ├── 总览            ← 保留，增强统计
│   ├── 同步源          ← 保留
│   ├── 同步记录        ← 保留，大幅增强
│   ├── 订阅管理        ← 新增
│   ├── Cookie 管理     ← 新增
│   ├── 定时计划        ← 保留
│   ├── 系统日志        ← 新增（独立日志页）
│   └── 同步设置        ← 保留，增加 NFO 等
└── 关于 YTSage
```

---

## 实施阶段

### 阶段一：数据模型扩展（store.py）

**文件**: `webui/sync/store.py`

1. `records` 表新增列:
   - `thumbnail_url TEXT` - 缩略图
   - `deleted_at REAL` - 软删除时间戳（null=未删除）
   - `nfo_generated INTEGER DEFAULT 0`

2. `targets` 表新增列:
   - `sync_mode TEXT DEFAULT 'sync'` — `'off' | 'sync' | 'full_sync'`
   - `save_path TEXT` — 独立保存路径覆盖
   - `channel_id TEXT` — YouTube channel ID
   - `avatar_url TEXT` — 频道头像
   - `last_sync_at REAL` — target 级最后同步时间

3. 新增表 `sync_daily_stats`:
   ```sql
   CREATE TABLE IF NOT EXISTS sync_daily_stats (
     date TEXT PRIMARY KEY,
     total_videos INTEGER DEFAULT 0,
     total_size INTEGER DEFAULT 0,
     liked_count INTEGER DEFAULT 0,
     playlist_count INTEGER DEFAULT 0,
     channel_count INTEGER DEFAULT 0,
     subs_count INTEGER DEFAULT 0,
     new_synced INTEGER DEFAULT 0
   );
   ```

4. 新增表 `sync_deleted_records`（软删除记录存储）:
   - 复用 records 表 + `deleted_at` 列即可，查询时 `WHERE deleted_at IS NOT NULL`

5. `_connect()` 中增加 `_migrate()` 函数，对已有数据库执行 `ALTER TABLE ADD COLUMN`（捕获 duplicate column 异常）

6. 扩展 `list_records()` 支持 `date_from`, `date_to`, `channel`, `kind` 过滤参数

7. 新增函数: `soft_delete_record()`, `restore_record()`, `list_deleted_records()`, `get_statistics()`, `get_daily_stats()`, `upsert_daily_stats()`

8. `DEFAULT_SETTINGS` 新增: `nfo_enabled`, `video_naming_template`, `share_link_enabled`

### 阶段二：后端新服务

#### 2a. 视频流服务

**文件**: `webui/sync/streaming.py`（新建）

- `stream_video(video_id)` → 返回 `StreamingResponse`，支持 HTTP Range
- 路径安全校验复用 `system_service.is_path_allowed()`
- 从 records 表查 `file_path`，校验文件存在
- MIME 类型: `video/mp4`, `video/webm`

**routes.py 新增**:
- `GET /api/sync/stream/{video_id}` — 视频流（使用 `get_user_allow_query_token` 认证，支持 `<video>` 标签直接播放）
- `HEAD /api/sync/stream/{video_id}` — 返回文件大小/类型

#### 2b. NFO 生成服务

**文件**: `webui/sync/nfo_service.py`（新建）

- `generate_nfo(record: dict, output_dir: Path)` → 生成 `.nfo` XML 文件
- 格式兼容 Emby/Jellyfin（参考 Kodi NFO 规范）
- 包含: title, plot, dateadded, studio(channel), genre, uniqueid(video_id)
- 参考 dysync 的 `NfoFileGenerator.cs`

**routes.py 新增**:
- `POST /api/sync/nfo/generate/{rid}` — 单条生成
- `POST /api/sync/nfo/generate-batch` — 批量生成

#### 2c. 订阅管理服务

**文件**: `webui/sync/subscription_service.py`（新建）

- `pull_subscriptions(profile)` — 用 yt-dlp `--flat-playlist` 抓取 `https://www.youtube.com/feed/subscriptions`，解析频道列表
- `sync_channel(profile, target, channel_id)` — 同步单个频道
- 复用 `yt_dlp_finder.get_yt_dlp_path()` 和 `analysis_service._sync_run()`

**routes.py 新增**:
- `POST /api/sync/subscriptions/pull` — 拉取订阅列表
- `PUT /api/sync/targets/{tid}/sync-mode` — 切换同步状态（off/sync/full_sync）
- `PUT /api/sync/targets/{tid}/save-path` — 修改保存路径
- `POST /api/sync/subscriptions/add` — 手动添加频道

#### 2d. Cookie 管理增强

**routes.py 新增**:
- `GET /api/sync/cookies/status` — 所有 profile 的 cookie 有效性状态
- `POST /api/sync/cookies/check/{pid}` — 检测指定 profile 的 cookie（用 yt-dlp 试访问）
- `POST /api/sync/cookies/detect-browser` — 检测浏览器中可用的 YouTube cookie

#### 2e. 统计 API

**routes.py 新增**:
- `GET /api/sync/statistics` — 总视频数、存储总量、各类型计数、作者 Top N
- `GET /api/sync/statistics/trend` — 7/30 天同步趋势数据
- `GET /api/sync/statistics/authors` — 作者排行（按视频数）

#### 2f. 记录增强 API

**routes.py 新增**:
- `POST /api/sync/records/batch-redownload` — 批量重新下载
- `POST /api/sync/records/batch-delete` — 批量软删除
- `POST /api/sync/records/{rid}/restore` — 恢复软删除
- `GET /api/sync/records/deleted` — 已删除记录列表
- `POST /api/sync/records/{rid}/share` — 生成分享链接
- `GET /api/sync/share/{token}` — 分享链接播放（匿名）

#### 2g. 日志独立页面 API

复用已有 `log_service.py`，新增:
- `GET /api/sync/logs/files` — 同步相关日志文件列表（可复用 log_service）
- `GET /api/sync/logs/read` — 增量读取日志

> 注: YTSage 已有 `/api/logs/files` 和 `/api/logs/read`，这里直接复用，前端新建独立页面即可。

### 阶段三：同步引擎增强（engine.py）

**文件**: `webui/sync/engine.py`

1. `_finalize_job()` 增强: 下载完成后更新 `sync_daily_stats`
2. `run_profile()` 增强: 完成后调用 `upsert_daily_stats()` 归档当日统计
3. 支持 `sync_mode` 逻辑: `off` 跳过, `sync` 仅新视频, `full_sync` 全量
4. 下载完成后根据 `nfo_enabled` 设置调用 `nfo_service.generate_nfo()`
5. 记录 `thumbnail_url`: 从 flat-playlist entry 中提取缩略图 URL 存入 records

### 阶段四：前端实现

#### 4a. API 层

**文件**: `webui/client/src/api/sync.js`

新增所有对应后端新端点的调用函数。

#### 4b. 路由 & 菜单

**文件**: `webui/client/src/router/index.js`

新增路由:
```js
{ path: 'sync/dashboard', component: () => import('@/views/sync/SyncDashboard.vue') },
{ path: 'sync/subscriptions', component: () => import('@/views/sync/SyncSubscriptions.vue') },
{ path: 'sync/cookies', component: () => import('@/views/sync/SyncCookies.vue') },
{ path: 'sync/logs', component: () => import('@/views/sync/SyncLogs.vue') },
```

**文件**: `webui/client/src/views/Layout.vue`

修改 `<el-sub-menu index="/sync">` 内的菜单项顺序，增加新项。同时更新 `pageTitle` computed。

#### 4c. 新增页面

**SyncDashboard.vue**（新建）:
- 统计卡片行: 总视频数、存储总量、各类型计数（liked/playlist/channel/subs）
- 7天同步趋势图: 使用纯 CSS/SVG 折线图（不引入 ECharts 依赖，保持轻量）
- 作者 Top 10 表格: channel 名 + 视频数

**SyncSubscriptions.vue**（新建）:
- 频道列表 el-table: 频道名、头像、同步状态（off/sync/full_sync 三态切换）、保存路径、最后同步时间
- 操作: 拉取订阅列表按钮、添加非订阅频道、立即同步单频道
- 复用现有 `listTargets()` + 新增 `pullSubscriptions()`, `updateSyncMode()`

**SyncCookies.vue**（新建）:
- Profile Cookie 状态卡片列表: 每个 profile 显示 cookie 来源、状态、最后检测时间
- 检测按钮: 调用 yt-dlp 验证 cookie 有效性
- 浏览器检测按钮: 检测本机浏览器中的 YouTube cookie

**SyncLogs.vue**（新建）:
- 复用已有 `/api/logs/files` 和 `/api/logs/read` 端点
- 文件选择下拉 + 实时日志显示区 + 自动滚动
- 参考 About.vue 中已有的 log panel 逻辑

#### 4d. 新增组件

**VideoPlayerDialog.vue**（新建）:
- el-dialog 包裹 `<video>` 标签
- src 指向 `/api/sync/stream/{video_id}?token=xxx`
- 支持 Range 请求（浏览器原生 `<video>` 支持）
- 显示视频标题、频道、大小

#### 4e. 现有页面增强

**SyncOverview.vue** 增强:
- 添加统计卡片行（从 `/api/sync/statistics` 获取）
- 保留现有 recent runs 表格

**SyncRecords.vue** 增强:
- 添加过滤器面板: 日期范围、作者、类型下拉
- 操作列增加: 播放按钮（打开 VideoPlayerDialog）、复制路径、分享链接
- 批量操作栏: 批量重新下载、批量删除、批量排除
- 新增 el-drawer: 已删除视频列表，支持恢复
- 表格行增加缩略图显示

**SyncSettings.vue** 增强:
- 新增 NFO 设置区: 启用/禁用 NFO 生成开关
- 新增视频命名模板输入
- 新增分享链接开关

#### 4f. i18n 文案

**文件**: `webui/client/src/i18n/index.js`

在 `WEB_EXTRA` 的 `web.sync` 下新增所有新键（中英文）:
- 菜单: `dashboard`, `subscriptions`, `cookies`, `sync_logs`
- 统计: `stat_total_videos`, `stat_storage`, `stat_liked`, ...
- 看板: `trend_7days`, `author_stats`, `top_authors`
- 记录增强: `play`, `copy_path`, `share_link`, `batch_redownload`, `batch_delete`, `deleted_drawer`, `restore`
- 过滤器: `filter_date`, `filter_author`, `filter_type`
- Cookie: `cookie_status`, `cookie_valid`, `cookie_expired`, `cookie_check`
- 订阅: `sub_sync_off`, `sub_sync_on`, `sub_sync_full`, `sub_pull`, `sub_add_manual`
- NFO: `nfo_enabled`, `nfo_generate`

### 阶段五：调度器增强（scheduler.py）

**文件**: `webui/sync/scheduler.py`

1. 每日统计归档: 在 `_runner()` 中增加每日 00:05 归档 `sync_daily_stats`
2. Cookie 定期检查: 每天检查一次所有 profile 的 cookie 有效性

---

## 关键文件清单

| 文件 | 操作 |
|------|------|
| `webui/sync/store.py` | 修改 - 数据模型扩展、迁移函数、新 CRUD |
| `webui/sync/engine.py` | 修改 - 统计归档、NFO 集成、sync_mode |
| `webui/sync/routes.py` | 修改 - 新增 ~15 个 API 端点 |
| `webui/sync/scheduler.py` | 修改 - 统计归档、cookie 检查 |
| `webui/sync/streaming.py` | 新建 - 视频流服务 |
| `webui/sync/nfo_service.py` | 新建 - NFO 生成 |
| `webui/sync/subscription_service.py` | 新建 - 订阅管理 |
| `webui/client/src/api/sync.js` | 修改 - 新增 API 调用 |
| `webui/client/src/router/index.js` | 修改 - 新增 4 条路由 |
| `webui/client/src/views/Layout.vue` | 修改 - 菜单增加新项 + pageTitle |
| `webui/client/src/views/sync/SyncDashboard.vue` | 新建 |
| `webui/client/src/views/sync/SyncSubscriptions.vue` | 新建 |
| `webui/client/src/views/sync/SyncCookies.vue` | 新建 |
| `webui/client/src/views/sync/SyncLogs.vue` | 新建 |
| `webui/client/src/views/sync/VideoPlayerDialog.vue` | 新建 |
| `webui/client/src/views/sync/SyncOverview.vue` | 修改 - 增加统计卡片 |
| `webui/client/src/views/sync/SyncRecords.vue` | 修改 - 大幅增强 |
| `webui/client/src/views/sync/SyncSettings.vue` | 修改 - 增加 NFO 等设置 |
| `webui/client/src/i18n/index.js` | 修改 - 新增文案 |

## 复用的现有模块

| 模块 | 复用方式 |
|------|---------|
| `download_manager.start_download()` | 同步下载、批量重新下载均通过此入口 |
| `analysis_service._sync_run()` | 执行 yt-dlp 命令（订阅列表拉取等） |
| `event_bus` | 下载完成事件更新 records（已实现） |
| `cookie_store` | Cookie 文件存储 |
| `system_service.is_path_allowed()` | 视频流路径安全校验 |
| `system_service.reveal_in_folder()` | "在文件管理器中显示" |
| `log_service` | 日志查看页面数据源 |
| `yt_dlp_finder.get_yt_dlp_path()` | 所有 yt-dlp 调用 |

## 验证方案

1. **后端验证**: `python -c "from webui.sync import store, routes, engine"` 确认无 import 错误
2. **数据库迁移**: 启动服务后检查 `ytsage_sync.db` 新表和新列是否创建
3. **前端构建**: `cd webui/client && npm run build` 确认无编译错误
4. **功能验证**:
   - 创建 profile + target → 执行同步 → 检查 records 和统计
   - 在记录页点击播放 → 视频在弹窗中播放
   - 切换订阅频道同步状态 → 验证 sync_mode 生效
   - 检测 Cookie → 显示有效性状态
   - 导出/导入配置 → 验证数据完整性
5. **磁盘验证**: 构建前用 `rg` 核实关键改动已落盘（项目已知 Edit 工具有偶发静默丢失问题）
