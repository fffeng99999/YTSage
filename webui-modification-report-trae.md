# YTSage WebUI 修改汇总报告

> 生成日期：2026-09-08
> 数据来源：项目记忆（project_memory + 20260906–20260908 全部会话记录）与 git 提交历史
> 覆盖范围：YTSage Web UI 从零创建到 7 模块重构的全部修改操作、Bug 修复、经验教训

---

## 一、项目总览

将 YTSage 桌面 GUI（PySide6）用 Vue3 重写为 Web 控制界面，核心约束：

- **零修改官方源码**：所有改动为新增文件（`webui/`、`run_webui.py`）与 `.gitignore`，官方 `git pull` 无冲突
- **优雅降级**：对官方模块的导入全部 `try/except` 包裹，无 PySide6/Loguru 时可独立运行
- **可复用官方数据层**（ConfigManager / HistoryManager / 语言文件，经 `official_bridge.py` 调用）；官方业务层（下载/分析/更新）与 Qt 强耦合无 API，Web 端独立复刻并带"对标官方文件:行号"注释
- **新功能只做"新增式"改动**，禁止删除/修改现有功能；下载统一走 `POST /api/download` + WS 任务体系

### 技术栈与运行环境

| 项 | 说明 |
|----|------|
| 后端 | FastAPI + uvicorn（Python 3.12.10 venv，系统默认 3.14 超出不兼容） |
| 前端 | Vue3 + Element Plus + Pinia + vue-i18n，`npm run build` → dist/ 由 FastAPI 静态服务 |
| 启动 | `.venv\Scripts\python run_webui.py`，端口 8765，默认密码 `ytsage` |
| yt-dlp | CLI 子进程调用（无 python 模块），位于 `%LOCALAPPDATA%\YTSage\bin` |
| 数据 | 与桌面版共用 `%LOCALAPPDATA%\YTSage\`（ytsage_config.json / data\ytsage_history.db） |
| 改动生效 | 后端改动需重启；前端改动需 npm run build（index.html 已设 no-store） |

---

## 二、修改操作时间线（按会话汇总）

### 2026-09-06 · 从零搭建与核心功能

| # | 操作 | 关键文件 | 结果/要点 |
|---|------|----------|-----------|
| 1 | 创建 Web 控制界面（零冲突架构） | `webui/` 全目录 + `run_webui.py` | 独立文件夹结构、WebSocket 实时进度、独立配置文件 |
| 2 | 创建 venv、安装依赖、启动 | `webui/requirements.txt` | /api/health ok，yt-dlp 2026.08.19 + ffmpeg 9.0.1 识别 |
| 3 | .gitignore 补 Node.js 规则 | `.gitignore` | node_modules/、npm-debug.log*、yarn/pnpm 日志、.vite/；package-lock.json 故意保留提交 |
| 4 | 修复语言切换 "ConfigManager not available" | `webui/requirements.txt` | 根因：venv 缺 loguru 导致官方导入链断裂；补装后 official_available=true |
| 5 | 修复登录失败 | `Login.vue` | 根因：密码含不可见空白字符；加 trim() 处理 |
| 6 | Cookie 由"文件路径"改为"文本内容"填写 | `cookie_store.py`、`server.py`、`Tools.vue` | 保存至 `%APPDATA%\YTSage\cookies.txt`（0600 权限），同步到官方配置供桌面版使用 |
| 7 | 质量排序改为从好到差 | `analysis.js` | 视频按 height、音频按 abr 降序，对齐官方 GUI get_quality(reverse=True) |
| 8 | 修复封面不显示 + 进度卡 0 | `server.py`、`download_manager.py` | 封面：thumbnail 接口改公开（img 标签不带 Authorization）；进度：yt-dlp 加 `--newline`（非终端环境 \r 进度行 readline 读不到） |
| 9 | 修复 Jobs 页标题乱码 | `download_manager.py`、`command_service.py` | Windows 冻结版 yt-dlp 输出用系统 ANSI 代码页(cp936)，PYTHONIOENCODING 无效，需按 ACP 解码 |
| 10 | Dashboard 下载块移到分析块下方 | `Dashboard.vue` | 仅调整独立 yts-card 相对位置，不嵌套、内部内容不动 |
| 11 | Linux 初始化配置向导 | `config_store.py`、`official_bridge.py`、`Setup.vue` | 3 步向导（语言/密码/配置）；standalone 与 shared 双模式；未完成向导 API 返回 428 强制跳转；Windows 现有安装自动迁移 shared |
| 12 | 新增批量下载与频道下载页面 | `Batch.vue`、`channel_service.py` | analyze_channel 翻页（--flat-playlist --playlist-end N）、analyze_batch Semaphore(3)；频道下载走单任务播放列表路径 |
| 13 | 端到端验证 + 6 项反馈修复 | 多文件 | Jobs 翻译条件、统一走 /api/download 任务体系、编码优先级 av01>vp09>avc1、频道分页 --playlist-start/end、已选置顶跨页保留、全局设置贯通 |

### 2026-09-07 · 设置增强与更新器

| # | 操作 | 关键文件 | 结果/要点 |
|---|------|----------|-----------|
| 1 | 缓存/嵌入面板等 4 项修复 | `Dashboard.vue`、`url_utils.py` | EmbedOptionsPanel 漏导入致弹层空白；SponsorBlock 后处理溢出 bug 的错误映射；新增 FilenameBuilder.vue 文件名拖拽构建 |
| 2 | 会话级输入保留 + 粘贴按钮 | `useSessionRef.js`、`useClipboard.js` | sessionStorage 键 ytsage_session_dash_url/batch_urls/channel_url；clipboard API 仅 https/localhost，非安全上下文回退手动粘贴对话框 |
| 3 | 编码优先级拖块设置 | `CodecPriorityBuilder.vue`、`settings_service.py`、`Batch.vue` | 设置项 codec_priority（校验仅 av01/vp09/avc1、去重保序），池中所剩编码作兜底；批量按 codecOrder 挑选、频道生成 yt-dlp 链选择器 |
| 4 | PostgreSQL 可行性报告（未动代码） | — | 结论：有条件可行，作可选影子库；盘点 7 个持久化点；下载任务与分析缓存最适合迁移 |
| 5 | FFmpeg 更新逻辑重做 | `updater_service.py`(webui 层)、`Updater.vue` | 官方 install_ffmpeg_windows 已装即 return True 无法更新 → 新增 ffmpeg_update_sync：gyan.dev zip → SHA256 → 解压 → 数字排序选最新 bin → 会话 PATH 前置 + winreg 写 HKCU Path（禁 setx 防 1024 截断）+ WM_SETTINGCHANGE 广播；版本比较需正则取前导数字 |
| 6 | 全插件统一更新 + 版本回退 | `updater_service.py`、`Updater.vue`、`official_bridge.py` | yt-dlp/ffmpeg/deno 统一 ffmpeg 式检查/安装；版本历史 `%LOCALAPPDATA%\YTSage\data\update_history\manifest.json`，交换式回退、每组件最多 5 个归档；修复 YTDLP_DOWNLOAD_URL 未导出 bug |
| 7 | 每视频独立文件夹 | `download_manager.py`、`thumbnail_service.py` | 输出模板改为 下载目录/视频标题/（视频、description、字幕、封面同放）；cleanup 递归清 .part；_find_final_file 用 rglob；filename_format 仍作文件夹内文件名 |
| 8 | 并发控制重构（全局队列） | `download_manager.py`、`Settings.vue`、`Batch.vue` | 原"并发连接数"实为 yt-dlp -N 分片数、批量页并发仅前端本地排队 → 新增 max_concurrent_downloads(1–10, 默认1)，DownloadManager._queue + _pump() 调度，超槽位 status='queued'；批量页一次性提交全部任务 |
| 9 | 并发设置 i18n 修复 | `webui/client/src/i18n/index.js` | 根因：/api/i18n/{lang} 有 _LANG_CACHE 进程内缓存，写官方语言文件需重启后端，用户未重启显示原始键名 → Web 专属文案改放前端 WEB_EXTRA，官方语言文件恢复原样 |
| 10 | 修复 "unknown setting" 保存报错 | — | 根因：8765 端口上旧进程（系统 Python 启动）未退出，新代码未生效 → 结束旧进程、用 venv 重启后验证通过 |

### 2026-09-08 · 字幕 429 修复与 7 模块重构

| # | 操作 | 关键文件 | 结果/要点 |
|---|------|----------|-----------|
| 1 | 修复字幕 429 杀死整个任务 | `download_manager.py` | 根因：yt-dlp 先写字幕，timedtext 429 默认 abort → build_ytdlp_command 统一加 `--ignore-errors`；注意 --no-abort-on-error 与其写同一参数且值为 'only_download' 仍 raise，**绝不可同时用**；完成判定改为"必须产出媒体文件"（rc==0 无文件→error） |
| 2 | 7 模块重构与 Bug 治理 | 约 26 个文件（见下） | 全部完成并通过 py_compile / 导入冒烟 / npm build / rg 磁盘核实 |

#### 7 模块重构明细

| 模块 | 内容 |
|------|------|
| 1. 进程生命周期 | 跨平台进程树终止（Windows `taskkill /F /T` + CREATE_NEW_PROCESS_GROUP；POSIX start_new_session + killpg）；清理 .part/.ytdl/.temp；asyncio 非阻塞管道读取 |
| 2. 并发与持久化 | 保留共享 SQLite（WAL + busy_timeout=5000 + 分页）；config_store.py 与 auth.py 加原子写 + 文件锁 |
| 3. Headless 解耦 | 确认零 GUI 导入；yt-dlp/ffmpeg 检测实现四级回退链 |
| 4. 安全 | 禁 shell=True；thumbnail_service 路径白名单；Cookie 数据脱敏；局域网模式强制密码要求 |
| 5. 状态机 | 下载阶段细化（parsing/merging/post_processing）；error_code 分类；WS 连接泄漏治理 |
| 6. 前端性能/远程 | History 后端分页；Batch 虚拟滚动；环境自适应文件操作（本地"打开文件夹" vs 远程"直接下载"）；WS 指数退避重连 |
| 7. 高级功能 | 批量筛选器、Cookie 导入向导、重试/限速设置 |

重构中的事故与修复：`server.py` 丢失 `import sys` 已补；`Jobs.vue` 误整文件重写已 `git checkout` 回滚并改为最小编辑。

---

## 三、git 提交记录（WebUI 专属）

```
5471fca fix(download): 修复字幕下载失败导致任务中断的问题
296fe47 refactor(webui): 重构并发下载逻辑，替换旧的单页并发设置
6006605 refactor(webui): 调整缩略图保存逻辑与下载目录结构
5b821d2 feat: 添加组件版本回退功能，支持yt-dlp/ffmpeg/deno
902791d feat(webui): add FFmpeg update support and improve updater UI/UX
0e00a47 feat(webui): 添加视频编码优先级设置与剪贴板优化
75afb2f feat: 新增频道分页下载、文件名构建器与多语言优化
22b99ed feat(batch-channel): 新增批量和频道下载页面
ed5c46f feat(webui): add first-run setup wizard and multi-mode config storage
4a0a324 / 6d809b5 / 82a0c07  初版 WebUI（前后端）
```

7 模块重构的改动（约 26 个文件，含新增 `useEnv.js`、`file_utils.py`）目前处于**已暂存未提交**状态。

---

## 四、关键经验教训（避坑清单）

1. **Edit 工具偶发"报成功但未落盘"**：同轮多个 Edit 时个别编辑静默丢失 → 构建前 `rg -n <关键改动> <文件>` 核实磁盘内容再 build
2. **vue-i18n 文案含 `@` 必须写 `{'@'}`**：否则整个组件渲染失败 "Invalid linked format"
3. **SponsorBlock + 字幕文件**触发 yt-dlp 上游 bug "Result too large"（issue #9929）→ 批量/频道页 SponsorBlock 默认关闭
4. **Web 专属 i18n 文案必须放前端 WEB_EXTRA**，不写官方 `ytsage/languages/*.json`（后端 _LANG_CACHE 需重启才生效，且保持官方文件原样）
5. **`--ignore-errors` 与 `--no-abort-on-error` 绝不可同时用**（同参数覆盖，后者值 'only_download' 仍 raise）
6. **downloadStore.onFinished 监听器泄漏**（永不移除）→ 批量任务状态用 `watch(downloadStore.jobs)`
7. **flat-playlist 频道条目无顶层 thumbnail** → 用 `i.ytimg.com/vi/{id}/hqdefault.jpg`；频道头像在 yt3.ggpht.com 不在代理白名单
8. **重启后端必须确认旧进程退出且用 venv 启动**，否则旧进程占端口导致改动"看起来没生效"
9. **浏览器验证看到旧 UI** → 先核对 dist/assets/*.js chunk hash，用 ?v=xxx 破缓存
10. **整文件重写有截断风险** → 优先最小编辑；并发下载中暂停中的任务仍占槽位

---

## 五、当前状态

- 程序运行于 `http://localhost:8765`（密码 `ytsage`），/api/health 全绿：official_available=true、history_available=true、missing_binaries 为空
- 局域网 + 默认密码提示为模块 4 预期行为，建议在设置页修改密码
- 全部 7 模块重构完成并验证；前端 build 通过；官方源码保持零改动

---

*— End of report —*