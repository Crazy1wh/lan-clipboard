#!/usr/bin/env python3
"""局域网剪贴板 - LAN Clipboard
FastAPI + SQLite，支持文字/图片/文件，历史记录，无需认证。
"""
import os
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "clipboard.db"

MAX_HISTORY = int(os.getenv("MAX_HISTORY", "200"))      # 保留的历史条数
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "100"))      # 单文件大小上限 MB
MAX_DISK_GB = float(os.getenv("MAX_DISK_GB", "10"))     # 数据目录总占用上限 GB，超出自动清理最旧
PRUNE_TARGET_RATIO = 0.9                                # 清理到上限的 90%，避免频繁触发

app = FastAPI(title="LAN Clipboard")


# ---------- 初始化 ----------
def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        type        TEXT NOT NULL,          -- text | image | file
        content     TEXT,                   -- 文字内容
        filename    TEXT,                   -- 原始文件名
        stored_name TEXT,                   -- 磁盘存储名
        size        INTEGER,
        ip          TEXT,
        created_at  REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS groups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        sort_order  INTEGER DEFAULT 0,
        created_at  REAL
    )""")
    # 兼容旧库：补充新增列
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    if "deleted" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN deleted INTEGER DEFAULT 0")
    if "starred" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN starred INTEGER DEFAULT 0")
    if "group_id" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN group_id INTEGER")
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def delete_row(conn, row):
    """删除一条记录，连带清理磁盘文件。"""
    if row["stored_name"]:
        try:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
        except OSError:
            pass
    conn.execute("DELETE FROM items WHERE id=?", (row["id"],))


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def prune(conn):
    """条数软上限 + 磁盘容量上限，超限时优先物理删已隐藏（回收站），再删最旧（连带磁盘文件）。"""
    # 1) 条数限制：防文字类条目无限增长
    rows = conn.execute(
        "SELECT id, stored_name FROM items ORDER BY id DESC LIMIT -1 OFFSET ?",
        (MAX_HISTORY,),
    ).fetchall()
    for r in rows:
        delete_row(conn, r)
    conn.commit()
    # 2) 容量限制：超过 MAX_DISK_GB 就删最旧，直到降到上限的 90%
    limit = MAX_DISK_GB * 1024 ** 3
    target = limit * PRUNE_TARGET_RATIO
    def oldest_row(prefer_deleted):
        if prefer_deleted:
            return conn.execute(
                "SELECT id, stored_name FROM items WHERE deleted=1 ORDER BY id ASC LIMIT 1"
            ).fetchone()
        return conn.execute(
            "SELECT id, stored_name FROM items ORDER BY id ASC LIMIT 1"
        ).fetchone()

    while dir_size(DATA_DIR) > limit:
        r = oldest_row(prefer_deleted=True) or oldest_row(prefer_deleted=False)
        if r is None:
            break
        delete_row(conn, r)
        conn.commit()
        if dir_size(DATA_DIR) <= target:
            break


def row_to_dict(r):
    return {
        "id": r["id"],
        "type": r["type"],
        "content": r["content"],
        "filename": r["filename"],
        "size": r["size"],
        "ip": r["ip"],
        "created_at": r["created_at"],
        "deleted": r["deleted"],
        "starred": r["starred"],
        "group_id": r["group_id"],
        "group_name": r["group_name"] if "group_name" in r.keys() else None,
        "url": f"/files/{r['stored_name']}" if r["stored_name"] else None,
    }


# ---------- 页面 ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


# ---------- API ----------
@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


@app.get("/api/items")
def list_items(
    after_id: int = 0,
    limit: int = 100,
    deleted: int = 0,
    starred: int = 0,
    group_id: int | None = None,
):
    """历史列表。默认未隐藏；deleted=1 看回收站；starred=1 看常用；group_id 看分组。
    after_id>0 时只返回比它新的条目（轮询用）。"""
    conds = ["i.deleted=?"]
    params: list = [deleted]
    if starred:
        conds.append("i.starred=1")
    if group_id is not None:
        conds.append("i.group_id=?")
        params.append(group_id)
    where = " AND ".join(conds)
    base = "SELECT i.*, g.name AS group_name FROM items i LEFT JOIN groups g ON i.group_id=g.id"
    conn = get_db()
    if after_id:
        rows = conn.execute(
            f"{base} WHERE i.id>? AND {where} ORDER BY i.id DESC LIMIT ?",
            (after_id, *params, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"{base} WHERE {where} ORDER BY i.id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    conn.close()
    return {"items": [row_to_dict(r) for r in rows]}


def escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@app.get("/api/search")
def search(q: str = "", limit: int = 100):
    """全局搜索：匹配文字内容或文件名（不区分大小写），不含已隐藏。"""
    q = (q or "").strip()
    if not q:
        return {"items": []}
    pattern = f"%{escape_like(q)}%"
    conn = get_db()
    rows = conn.execute(
        "SELECT i.*, g.name AS group_name FROM items i LEFT JOIN groups g ON i.group_id=g.id "
        "WHERE i.deleted=0 AND (i.content LIKE ? ESCAPE '\\' OR i.filename LIKE ? ESCAPE '\\') "
        "ORDER BY i.id DESC LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()
    conn.close()
    return {"items": [row_to_dict(r) for r in rows]}


@app.get("/api/groups")
def list_groups():
    """分组列表（含每组未隐藏条目数）。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM items i WHERE i.group_id=g.id AND i.deleted=0) AS count "
        "FROM groups g ORDER BY g.sort_order, g.id"
    ).fetchall()
    conn.close()
    return {"groups": [dict(r) for r in rows]}


class GroupIn(BaseModel):
    name: str


@app.post("/api/groups")
def create_group(body: GroupIn):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "分组名不能为空"}, status_code=400)
    conn = get_db()
    conn.execute("INSERT INTO groups (name, created_at) VALUES (?,?)", (name, time.time()))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.put("/api/groups/{group_id}")
def rename_group(group_id: int, body: GroupIn):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "分组名不能为空"}, status_code=400)
    conn = get_db()
    conn.execute("UPDATE groups SET name=? WHERE id=?", (name, group_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int):
    conn = get_db()
    conn.execute("UPDATE items SET group_id=NULL WHERE group_id=?", (group_id,))
    conn.execute("DELETE FROM groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/stats")
def stats():
    """数据占用统计：条数、磁盘占用、上限。"""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    used = dir_size(DATA_DIR)
    return {
        "count": count,
        "disk_used": used,
        "disk_limit": int(MAX_DISK_GB * 1024 ** 3),
    }


class TextIn(BaseModel):
    content: str


@app.post("/api/text")
def add_text(body: TextIn, request: Request):
    content = (body.content or "").strip()
    if not content:
        return JSONResponse({"ok": False, "error": "内容为空"}, status_code=400)
    ip = request.client.host if request.client else ""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO items (type, content, ip, created_at) VALUES (?,?,?,?)",
        ("text", content, ip, time.time()),
    )
    conn.commit()
    item = conn.execute(
        "SELECT i.*, g.name AS group_name FROM items i LEFT JOIN groups g ON i.group_id=g.id WHERE i.id=?",
        (cur.lastrowid,),
    ).fetchone()
    prune(conn)
    conn.close()
    return {"ok": True, "item": row_to_dict(item)}


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), kind: str = Form("file")):
    """上传图片或文件。kind: image | file（由前端按扩展名判断）"""
    data = await file.read()
    if not data:
        return JSONResponse({"ok": False, "error": "文件为空"}, status_code=400)
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        return JSONResponse(
            {"ok": False, "error": f"文件超过 {MAX_FILE_MB}MB 上限"}, status_code=413
        )
    ext = Path(file.filename or "file").suffix.lower()
    if kind == "image" and ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"):
        kind = "file"  # 不是图片就按普通文件存
    stored = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    (UPLOAD_DIR / stored).write_bytes(data)
    ip = request.client.host if request.client else ""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO items (type, filename, stored_name, size, ip, created_at) VALUES (?,?,?,?,?,?)",
        (kind, file.filename, stored, len(data), ip, time.time()),
    )
    conn.commit()
    item = conn.execute(
        "SELECT i.*, g.name AS group_name FROM items i LEFT JOIN groups g ON i.group_id=g.id WHERE i.id=?",
        (cur.lastrowid,),
    ).fetchone()
    prune(conn)
    conn.close()
    return {"ok": True, "item": row_to_dict(item)}


@app.get("/files/{stored_name}")
def get_file(stored_name: str):
    """下载/预览文件。"""
    p = UPLOAD_DIR / stored_name
    if not p.exists() or not p.is_file():
        return JSONResponse({"ok": False, "error": "文件不存在"}, status_code=404)
    conn = get_db()
    r = conn.execute(
        "SELECT * FROM items WHERE stored_name=?", (stored_name,)
    ).fetchone()
    conn.close()
    # 路径穿越防护：stored_name 必须是我们生成过的
    if r is None:
        return JSONResponse({"ok": False, "error": "文件不存在"}, status_code=404)
    if r["type"] == "image":
        return FileResponse(p)  # 浏览器按扩展名渲染
    return FileResponse(p, filename=r["filename"] or stored_name)


@app.delete("/api/items/{item_id}")
def delete_item(item_id: int):
    """软删除：移入已隐藏（回收站），可恢复。"""
    conn = get_db()
    r = conn.execute("SELECT id FROM items WHERE id=?", (item_id,)).fetchone()
    if r is None:
        conn.close()
        return JSONResponse({"ok": False, "error": "不存在"}, status_code=404)
    conn.execute("UPDATE items SET deleted=1 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/items/{item_id}/purge")
def purge_item(item_id: int):
    """彻底删除（含磁盘文件），不可恢复。"""
    conn = get_db()
    r = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if r is None:
        conn.close()
        return JSONResponse({"ok": False, "error": "不存在"}, status_code=404)
    delete_row(conn, r)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/items/{item_id}/restore")
def restore_item(item_id: int):
    conn = get_db()
    conn.execute("UPDATE items SET deleted=0 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/items/{item_id}/star")
def toggle_star(item_id: int):
    """切换常用收藏标记。"""
    conn = get_db()
    conn.execute("UPDATE items SET starred = 1 - starred WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


class GroupAssign(BaseModel):
    group_id: int | None = None


@app.post("/api/items/{item_id}/group")
def set_group(item_id: int, body: GroupAssign):
    """把条目归入分组（null = 未分组）。"""
    conn = get_db()
    conn.execute("UPDATE items SET group_id=? WHERE id=?", (body.group_id, item_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/items")
def clear_all():
    """清空所有内容（含已隐藏），物理删除。"""
    conn = get_db()
    rows = conn.execute("SELECT stored_name FROM items WHERE stored_name IS NOT NULL").fetchall()
    for r in rows:
        try:
            (UPLOAD_DIR / r["stored_name"]).unlink(missing_ok=True)
        except OSError:
            pass
    conn.execute("DELETE FROM items")
    conn.commit()
    conn.close()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

init()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8010")))
