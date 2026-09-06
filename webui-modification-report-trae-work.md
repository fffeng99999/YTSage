# YTSage Web UI 修改报告

> 生成日期：2026-09-06
> 改动性质：**纯新增文件**，零修改官方源码
> 目标：在不干扰官方源码同步（git pull）的前提下，为 YTSage 提供浏览器控制界面

---

## 一、变更范围总览

```
YTSage/
├── run_webui.py              ← 新增：一键启动脚本
└── webui/                    ← 新增：Web UI 模块（完整独立）
    ├── __init__.py
    ├── requirements.txt
    ├── auth.py
    ├── yt_dlp_finder.py
    ├── analysis_service.py
    ├── download_manager.py
    ├── server.py
    └── client/               ← 新增：Vue 3 前端
        ├── package.json
        ├── vite.config.js
        ├── index.html
        └── src/
            ├── main.js
            ├── App.vue
            ├── router/index.js
            ├── stores/auth.js
            ├── stores/download.js
            ├── api/http.js
            ├── api/auth.js
            ├── api/download.js
            ├── api/settings.js
            └── views/
                ├── Login.vue
                ├── Layout.vue
                ├── Dashboard.vue
                ├── Jobs.vue
                └── Settings.vue
```

**官方源码改动：0 个文件**（`git status` 仅显示以上两个 untracked 路径）

---

## 二、设计原则

| 原则 | 实现方式 |
|------|----------|
| 不修改官方代码 | 所有新增文件放在根目录 `webui/` 与 `run_webui.py`，不触碰 `ytsage/` 包内任何文件 |
| 可独立运行 | 后端模块对官方包的导入全部用 `try/except` 包裹；没有 PySide6/Loguru 时自动降级 |
| 命令构建同步官方 | `download_manager.py` 中的 `build_ytdlp_command()` 逐行对标官方 `DownloadThread._build_yt_dlp_command()` |
| 独立配置空间 | WebUI 密码/密钥存在 `%APPDATA%/YTSage/webui_config.json`，与官方 ConfigManager 分离 |
| 不阻塞官方更新 | 新增文件在独立目录，官方 `git pull` 不会产生冲突 |

---

## 三、后端模块详解

### 3.1 `webui/auth.py` — 密码认证

- 使用 HMAC-SHA256 签名 token，无额外依赖
- Token 有效期 7 天
- 默认密码 `ytsage`，首次登录后可在 Settings 页面修改
- 密码哈希与签名密钥独立存储，不写官方配置

### 3.2 `webui/yt_dlp_finder.py` — yt-dlp 路径查找

- **无 PySide6 依赖**，仅用 `shutil.which()` + Path 检查
- 搜索顺序：官方 App bin 目录 → 系统 PATH → 返回 `"yt-dlp"` 占位
- 复制了官方 `get_yt_dlp_path()` 的搜索逻辑但去除 Qt 依赖

### 3.3 `webui/analysis_service.py` — URL 分析

- 用 `subprocess.run()` 执行 `yt-dlp --dump-single-json --flat-playlist`
- 完整实现 playlist 检测、首视频格式补全、字幕列表提取
- 异步包装通过 `asyncio.to_thread()` 避免阻塞事件循环

### 3.4 `webui/download_manager.py` — 下载核心

- **核心命令构建 1:1 对标官方** `DownloadThread._build_yt_dlp_command()`，覆盖：
  - 格式选择（playlist / 单视频 / 仅音频）
  - 输出格式强制
  - 音频归一化
  - SponsorBlock
  - 字幕写入/嵌入
  - Cookie / 代理 / 限速 / 分段下载
  - 输出模板 / 并发分片
- 运行方式：`asyncio.create_subprocess_exec`（替代 QThread）
- 实时进度：行解析正则提取 `%`、速度、ETA、合并阶段等
- 广播机制：`asyncio.Queue` 注册给 WebSocket 连接，事件 push 而非 pull

### 3.5 `webui/server.py` — FastAPI 主应用

**API 路由（共 21 条）：**

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/auth/login` | 密码登录，返回 token |
| POST | `/api/auth/change-password` | 修改 WebUI 密码 |
| GET | `/api/auth/verify` | 验证 token |
| GET | `/api/health` | 系统状态（公开） |
| POST | `/api/analyze` | URL 分析 |
| POST | `/api/download` | 启动下载 |
| GET | `/api/jobs` | 列出所有任务 |
| GET | `/api/jobs/{id}` | 任务详情 |
| POST | `/api/jobs/{id}/cancel` | 取消下载 |
| POST | `/api/jobs/{id}/pause` | 暂停下载 |
| POST | `/api/jobs/{id}/resume` | 继续下载 |
| DELETE | `/api/jobs/{id}` | 删除任务记录 |
| GET | `/api/settings` | 读取设置 |
| POST | `/api/settings` | 更新设置 |
| WS | `/ws?token=xxx` | 实时事件推送 |
| GET | `/` | 静态前端（SPA 入口） |

**依赖降级策略：**

```python
try:
    from ytsage.utils.ytsage_constants import SUBPROCESS_CREATIONFLAGS, ...
except ImportError:
    SUBPROCESS_CREATIONFLAGS = 0
    MEDIA_EXTENSIONS = {...}
```

当官方包完整可用时，自动使用官方常量与 ConfigManager；缺失时使用内置默认值。

---

## 四、前端模块详解

**技术栈：** Vue 3 + Vite + Pinia + Vue Router + Element Plus + Axios

### 4.1 页面结构

| 页面 | 路由 | 功能 |
|------|------|------|
| Login | `/login` | 密码登录（渐变背景 + Element Plus 表单） |
| Dashboard | `/` | URL 输入 / 格式选择 / 下载控制 / 近期任务 |
| Jobs | `/jobs` | 所有下载任务列表，支持暂停/继续/取消/删除 |
| Settings | `/settings` | 系统状态、下载设置、代理设置、密码修改 |

### 4.2 状态管理

- `stores/auth.js` — token 持久化（localStorage），路由守卫检查
- `stores/download.js` — 任务列表状态，WebSocket 自动重连（3 秒）

### 4.3 WebSocket 集成

- 连接 URL：`ws(s)://host/ws?token=xxx`
- 事件类型：`job_created` / `job_update` / `job_finished` / `job_removed`
- 断线自动重连，重连后通过 REST `GET /api/jobs` 刷新全量

### 4.4 后端代理

Vite dev server 将 `/api` 和 `/ws` 代理到 `http://localhost:8765`，开发时前端 5173 + 后端 8765 并行运行。

---

## 五、启动方式

### 首次安装（后端依赖）

```bash
pip install -r webui/requirements.txt
```

### 构建前端

```bash
cd webui/client
npm install
npm run build
cd ../..
```

### 一键启动

```bash
# 方式 A：自动构建前端后启动
python run_webui.py --build-frontend

# 方式 B：仅启动后端（需要先手动构建前端）
python run_webui.py

# 方式 C：开发模式（后端 + 独立前端 dev server）
python run_webui.py --dev        # 后端 :8765
cd webui/client && npm run dev   # 前端 :5173，自动代理 /api /ws
```

启动后访问 `http://localhost:8765`，默认密码 `ytsage`。

---

## 六、API 测试结果

后端启动后使用 PowerShell `Invoke-RestMethod` 验证：

**GET /api/health** ✅
```json
{
  "status": "ok",
  "app_version": "5.5.0",
  "ytdlp_path": "C:\\Users\\userasus\\AppData\\Local\\YTSage\\bin\\yt-dlp.exe",
  "ytdlp_version": "2026.08.19",
  "ffmpeg_version": "ffmpeg version 9.0.1-essentials_build-...",
  "official_available": false
}
```

**POST /api/auth/login** ✅
```json
{
  "token": "{\"exp\":1789279441,\"iat\":1788674641}.1a00e46f...",
  "expires_in": 604800
}
```

FastAPI app 成功注册 **21 条路由**，启动无报错。

---

## 七、依赖清单

### Python（官方已有）

| 包 | 版本 | 用途 |
|----|------|------|
| requests | ≥2.32.5 | 官方已有 |
| packaging | ≥25.0 | 官方已有 |
| loguru | ≥0.7.3 | 官方已有（WebUI 用标准 logging 替代） |

### Python（WebUI 新增，`webui/requirements.txt`）

| 包 | 版本 | 用途 |
|----|------|------|
| fastapi | ≥0.111.0 | 异步 Web 框架 |
| uvicorn[standard] | ≥0.30.0 | ASGI 服务器 |
| pydantic | ≥2.0.0 | 请求模型校验 |

### Node.js（前端）

| 包 | 版本 | 用途 |
|----|------|------|
| vue | ^3.4.0 | UI 框架 |
| vue-router | ^4.3.0 | 路由 |
| pinia | ^2.1.7 | 状态管理 |
| axios | ^1.6.8 | HTTP 客户端 |
| element-plus | ^2.6.0 | UI 组件库 |
| @element-plus/icons-vue | ^2.3.1 | 图标 |
| vite | ^5.2.0 | 构建工具 |
| @vitejs/plugin-vue | ^5.0.0 | Vue 编译插件 |

---

## 八、官方更新时的注意事项

| 场景 | 处理 |
|------|------|
| `git pull` 拉官方更新 | **零冲突** — 新增文件全部在独立路径 |
| 官方升级 yt-dlp 版本 | 直接生效，WebUI 通过 CLI 调用 |
| 官方升级 ffmpeg | 直接生效，WebUI 通过 CLI 调用 |
| 官方修改 `DownloadThread` 命令逻辑 | 需在 `webui/download_manager.py` 同步修改 `build_ytdlp_command()`；但该函数有注释标注与官方的对应关系 |
| 官方新增下载参数 | 在 `DownloadRequest` Pydantic 模型与 `build_ytdlp_command()` 中补充 |

---

## 九、可选扩展

| 功能 | 当前状态 | 扩展方向 |
|------|----------|----------|
| 历史记录持久化 | 内存中 | 接入官方 `HistoryManager` 或独立 SQLite |
| 多语言/i18n | 中文硬编码 | 引入 Vue i18n，复用官方 `ytsage/languages/*.json` |
| 下载速度限制 | API 支持 | UI 增加对应输入控件 |
| 分段下载（Section） | API 支持 | UI 增加起止时间输入 |
| 批量 URL 队列 | 单任务 | REST 支持后前端加批量输入 |
| 移动端 PWA | SPA 已适配 | 加 manifest.json + service worker |

---

*— End of report —*
