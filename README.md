# 局域网剪贴板 (LAN Clipboard)

局域网内共享文字 / 图片 / 文件的网页剪贴板。打开网页即用，无需登录，多设备自动同步刷新，带历史记录。

## 功能

- 📝 文字：粘贴/输入即发，URL 自动转为可点链接
- 🖼 图片：Ctrl+V 直接粘贴剪贴板图片、拖拽或选择文件自动上传，历史里可点开大图
- 📎 文件：任意文件拖拽/粘贴/选择自动上传，一键下载，支持多文件
- 📤 分享：文件/图片一键生成二维码 + 自动复制链接，扫码即可下载（无需登录）
- 🔍 全局搜索：按文字内容或文件名搜索全部历史
- 🕘 历史记录：SQLite 持久化，保留最近 2000 条（可配），显示时间 + 来源 IP
- 💾 容量自管：数据总占用默认上限 10G，超出自动清理最旧内容（可配）
- 🔄 多设备同步：页面每 10 秒增量轮询，有新内容自动插入顶部并提示
- 🚫 无需认证：纯局域网信任环境

## 启动

Docker（推荐）：

    docker compose up -d --build

打开 http://<服务器IP>:8010 即可使用。

源码运行：

    pip install -r requirements.txt
    python app.py            # 默认 8010 端口

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| PORT | 8010 | 端口 |
| MAX_HISTORY | 2000 | 历史保留条数（防文字类无限增长） |
| MAX_FILE_MB | 100 | 单文件上传上限 MB |
| MAX_DISK_GB | 10 | 数据总占用上限 GB，超出自动清理最旧内容 |
| DATA_DIR | ./data | 数据目录（SQLite + 上传文件） |

## 技术栈

FastAPI + SQLite + 原生 JS 单页（无构建步骤）。数据全部在本地，不出局域网。

## 目录结构

    lan-clipboard/
    ├── app.py               # FastAPI 后端
    ├── static/index.html    # 前端单页
    ├── data/                # SQLite + uploads（自动生成）
    ├── requirements.txt
    ├── Dockerfile
    └── docker-compose.yml
