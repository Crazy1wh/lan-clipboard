# 局域网剪贴板 (LAN Clipboard)

局域网内共享文字 / 图片 / 文件的网页剪贴板。打开网页即用，无需登录，多设备自动同步刷新，带历史记录、回收站与分组。

## 功能

- 📝 文字：粘贴/输入即发，URL 自动转为可点链接
- 🖼 图片：Ctrl+V 直接粘贴剪贴板图片、拖拽或选择文件自动上传，历史里可点开大图
- 📎 文件：任意文件拖拽/粘贴/选择自动上传（无单文件限制，受总量约束），支持多文件、实时进度/速度/剩余时间显示
- 📤 分享：文件/图片一键生成二维码 + 自动复制链接，扫码即可下载（无需登录）
- 🗑 回收站：删除进入回收站（保留 7 天自动清理），可随时恢复或彻底删除
- 📁 分组与常用：自定义分组归类，⭐ 常用收藏，一键筛选
- 🏷 设备名：自动识别来源设备（反查局域网主机名，如 DESKTOP-XXX，查不到回退 UA 识别）
- 🔍 全局搜索：按文字内容或文件名搜索全部历史
- 🕘 历史记录：SQLite 持久化，保留最近 2000 条（可配），显示时间 + 设备名 + 来源 IP
- 💾 容量自管：数据总占用默认上限 10G（可配），超出自动清理最旧内容；上传受剩余容量动态约束
- 🔄 多设备同步：页面每 10 秒增量轮询，有新内容自动插入顶部并提示
- 📱 移动端适配：输入框不会自动缩放，操作按钮单行排布，支持拍照/相册上传
- 🚫 无需认证：纯局域网信任环境

## 启动

Docker（推荐）：

    docker compose up -d --build

打开 http://<服务器IP>:8010 即可使用。

源码运行：

    pip install -r requirements.txt
    python app.py            # 默认 8010 端口，可用 PORT 环境变量修改

预构建镜像（GitHub Actions 自动推送，推 main / v* 标签即触发）：

    docker pull ghcr.io/crazy1wh/lan-clipboard:latest
    docker run -d -p 8010:8010 -v ./data:/app/data ghcr.io/crazy1wh/lan-clipboard

## 配置（环境变量）

默认值见 `.env.example`，直接复制为 `.env` 即可用 docker compose 覆盖（`cp .env.example .env`），也可用系统环境变量传入。

| 变量 | 默认 | 说明 |
|------|------|------|
| PORT | 8010 | 服务端口（Docker 部署下改 .env 即可，ports 映射已用 \${PORT} 同步） |
| MAX_HISTORY | 2000 | 历史保留条数（防文字类无限增长） |
| MAX_DISK_GB | 10 | 数据总占用上限 GB。无单文件限制，上传受总量约束；超出自动清理最旧内容 |
| DATA_DIR | ./data | 数据目录（SQLite + 上传文件） |

## 目录结构

    lan-clipboard/
    ├── app.py               # FastAPI 后端
    ├── static/
    │   ├── index.html       # 前端单页
    │   └── vendor/qrcode.js # 二维码生成库（本地内嵌，无外网依赖）
    ├── scripts/             # hermes verify 本地验证包装脚本（开发用）
    ├── data/                # SQLite + uploads（自动生成，已 gitignore）
    ├── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml
    └── LICENSE              # MIT

## 技术栈

FastAPI + SQLite + 原生 JS 单页（无构建步骤、无 CDN 依赖）。二维码由本地 JS 生成，数据全部在本地，不出局域网。

## 安全提示

- 本工具**无认证、无加密**，仅限部署在可信局域网内使用
- 若需暴露到公网使用，请务必通过反向代理（如 Nginx/Caddy）加访问控制或 HTTPS

## License

[MIT](LICENSE) © Crazy1wh