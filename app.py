from __future__ import annotations

import cgi
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
import uuid
import zipfile
from collections import Counter
from flask import Flask, request, jsonify, send_from_directory, redirect
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.sqlite3"
CONFIG_PATH = DATA_DIR / "config.json"
STATIC_DIR = ROOT / "static"
MODEL_DIRS = [ROOT / "models", DATA_DIR / "models"]

DEFAULT_CATEGORIES = ["英雄攻略", "活动规则", "账号问题", "充值答疑", "故障排查"]
DEFAULT_TOP_K = 6
DEFAULT_THRESHOLD = 0.22
MIN_RELIABLE_SCORE = 0.22
DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_CONTEXT_TURNS = 10
HERO_ALIASES = {
    "凯": "铠",
    "铠皇": "铠",
    "鲁班": "鲁班七号",
    "后弈": "后羿",
}
DEFAULT_SYSTEM_CONFIG = {
    "chunkSize": DEFAULT_CHUNK_SIZE,
    "chunkOverlap": DEFAULT_CHUNK_OVERLAP,
    "defaultTopK": DEFAULT_TOP_K,
    "defaultThreshold": DEFAULT_THRESHOLD,
    "minReliableScore": MIN_RELIABLE_SCORE,
    "maxAnswerChars": 1200,
    "contextTurns": DEFAULT_CONTEXT_TURNS,
    "contextMaxChars": 2000,
    "retrievalTimeoutSeconds": 10,
    "answerTimeoutSeconds": 60,
    "maxUploadMb": 20,
    "vectorStorePath": str(DB_PATH),
    "requestTimeoutSeconds": 90,
    "vectorCacheStrategy": "memory",
    "responseCacheTtlSeconds": 60,
    "redisUrl": "",
    "llmEnabled": True,
    "llmProvider": "ollama",
    "answerMode": "enhanced",
    "ollamaUrl": "http://127.0.0.1:11434",
    "ollamaModel": "qwen2:7b-instruct-q4_0",
    "ollamaTemperature": 0.2,
    "onlineVendor": "",
    "onlineApiUrl": "",
    "onlineApiKey": "",
    "onlineModel": "",
    "fallbackAnswer": "未在知识库中找到相关答案，请换个问题试试。",
    "sensitiveWords": "",
    "refusalKeywords": "违法\n恶意\n攻击\n辱骂\n色情\n暴力\n诈骗\n外挂\n代练\n盗号",
    "refusalAnswer": "抱歉，这类问题我不能回答。你可以咨询账号、充值、活动、英雄玩法或知识库内的相关内容。",
    "dialogRules": "帮助=你可以询问账号问题、充值到账、活动奖励、英雄玩法、英雄克制关系，也可以输入“转人工”继续处理。\n版本=当前系统为王者荣耀客服知识库演示版，支持知识库检索、Ollama 增强回答、角色权限和对话日志。",
}
DEFAULT_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_LOGIN_FAILURES = 5
MAX_AVATAR_DATA_CHARS = 700_000
DEFAULT_ROLE_PERMISSIONS = {
    "超级管理员": ["*"],
    "知识库管理员": [
        "chat:use",
        "kb:read",
        "kb:write",
        "doc:read",
        "doc:write",
        "vector:manage",
    ],
    "普通用户": ["chat:use"],
}
PERMISSION_CATALOG = [
    {"key": "chat:use", "name": "使用对话机器人"},
    {"key": "kb:read", "name": "查看知识库"},
    {"key": "kb:write", "name": "管理知识库"},
    {"key": "doc:read", "name": "查看文档"},
    {"key": "doc:write", "name": "管理文档"},
    {"key": "vector:manage", "name": "管理向量"},
    {"key": "system:manage", "name": "管理系统配置"},
    {"key": "auth:manage", "name": "管理用户角色权限"},
    {"key": "log:read", "name": "查看日志"},
]
ROUTE_PERMISSIONS = [
    ("GET", re.compile(r"^/api/me$"), ""),
    ("PUT", re.compile(r"^/api/me$"), ""),
    ("GET", re.compile(r"^/api/permissions/catalog$"), "auth:manage"),
    ("GET", re.compile(r"^/api/users$"), "auth:manage"),
    ("POST", re.compile(r"^/api/users$"), "auth:manage"),
    ("PUT", re.compile(r"^/api/users/[^/]+$"), "auth:manage"),
    ("DELETE", re.compile(r"^/api/users/[^/]+$"), "auth:manage"),
    ("GET", re.compile(r"^/api/roles$"), "auth:manage"),
    ("POST", re.compile(r"^/api/roles$"), "auth:manage"),
    ("PUT", re.compile(r"^/api/roles/[^/]+$"), "auth:manage"),
    ("DELETE", re.compile(r"^/api/roles/[^/]+$"), "auth:manage"),
    ("GET", re.compile(r"^/api/kbs$"), "kb:read"),
    ("POST", re.compile(r"^/api/kbs$"), "kb:write"),
    ("PUT", re.compile(r"^/api/kbs/[^/]+$"), "kb:write"),
    ("DELETE", re.compile(r"^/api/kbs/[^/]+$"), "kb:write"),
    ("POST", re.compile(r"^/api/kbs/[^/]+/clone$"), "kb:write"),
    ("POST", re.compile(r"^/api/kbs/[^/]+/documents$"), "doc:write"),
    ("GET", re.compile(r"^/api/documents$"), "doc:read"),
    ("GET", re.compile(r"^/api/documents/[^/]+/preview$"), "doc:read"),
    ("PUT", re.compile(r"^/api/documents/[^/]+$"), "doc:write"),
    ("DELETE", re.compile(r"^/api/documents/[^/]+$"), "doc:write"),
    ("POST", re.compile(r"^/api/documents/batch-delete$"), "doc:write"),
    ("POST", re.compile(r"^/api/split-preview$"), "doc:read"),
    ("POST", re.compile(r"^/api/kb-test$"), "vector:manage"),
    ("POST", re.compile(r"^/api/chat$"), "chat:use"),
    ("GET", re.compile(r"^/api/vectors/preview$"), "vector:manage"),
    ("POST", re.compile(r"^/api/vectors/rebuild$"), "vector:manage"),
    ("POST", re.compile(r"^/api/vectors/normalize$"), "vector:manage"),
    ("POST", re.compile(r"^/api/vectors/deduplicate$"), "vector:manage"),
    ("GET", re.compile(r"^/api/system/config$"), "system:manage"),
    ("POST", re.compile(r"^/api/system/config$"), "system:manage"),
    ("GET", re.compile(r"^/api/ollama/models$"), "system:manage"),
    ("GET", re.compile(r"^/api/models$"), "kb:read"),
    ("POST", re.compile(r"^/api/models$"), "system:manage"),
    ("POST", re.compile(r"^/api/models/[^/]+/default$"), "system:manage"),
    ("GET", re.compile(r"^/api/logs$"), "log:read"),
]
DEFAULT_EMBEDDING_MODELS = [
    {
        "name": "local-keyword-vector",
        "path": "builtin://keyword-vector",
        "dimension": 384,
        "description": "内置关键词向量，适合离线演示和快速调试。",
        "is_default": 1,
    },
    {
        "name": "bge-small-zh-v1.5",
        "path": "models/bge-small-zh-v1.5",
        "dimension": 512,
        "description": "中文轻量 Embedding 模型，可用于本地批量向量化。",
        "is_default": 0,
    },
    {
        "name": "bge-base-zh-v1.5",
        "path": "models/bge-base-zh-v1.5",
        "dimension": 768,
        "description": "中文基础 Embedding 模型，召回质量更高但资源占用更大。",
        "is_default": 0,
    },
]


def now_ms() -> int:
    return int(time.time() * 1000)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        method, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if method != "pbkdf2_sha256":
        return False
    expected = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(expected, digest)


def normalize_permissions(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value]
    else:
        parsed = value
    if not isinstance(parsed, list):
        return []
    permissions = [str(item).strip() for item in parsed if str(item).strip()]
    if "*" in permissions:
        return ["*"]
    allowed = {item["key"] for item in PERMISSION_CATALOG}
    return sorted({item for item in permissions if item in allowed})


def has_permission(user: dict, permission: str) -> bool:
    if not permission:
        return True
    permissions = user.get("permissions") or []
    return "*" in permissions or permission in permissions


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT 'local-keyword-vector',
                status TEXT NOT NULL DEFAULT 'active',
                deleted INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                tokens TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
                FOREIGN KEY (doc_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS chat_logs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                kb_id TEXT,
                sources TEXT NOT NULL,
                score REAL NOT NULL,
                latency_ms INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS embedding_models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                path TEXT NOT NULL DEFAULT '',
                dimension INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vector_metadata (
                chunk_id TEXT PRIMARY KEY,
                dimension INTEGER NOT NULL DEFAULT 0,
                norm REAL NOT NULL DEFAULT 0,
                normalized_terms TEXT NOT NULL DEFAULT '[]',
                normalized_at INTEGER NOT NULL,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id)
            );

            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                permissions TEXT NOT NULL DEFAULT '[]',
                builtin INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL DEFAULT '',
                avatar_data TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'enabled',
                role_id TEXT NOT NULL,
                allowed_kb_ids TEXT NOT NULL DEFAULT '[]',
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                last_login_at INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (role_id) REFERENCES roles(id)
            );

            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(knowledge_bases)").fetchall()]
        if "department" not in columns:
            conn.execute("ALTER TABLE knowledge_bases ADD COLUMN department TEXT NOT NULL DEFAULT ''")
        user_columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "allowed_kb_ids" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN allowed_kb_ids TEXT NOT NULL DEFAULT '[]'")
        if "display_name" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        if "avatar_data" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN avatar_data TEXT NOT NULL DEFAULT ''")
        conversation_columns = [row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()]
        if "user_id" not in conversation_columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        log_columns = [row["name"] for row in conn.execute("PRAGMA table_info(chat_logs)").fetchall()]
        if "user_id" not in log_columns:
            conn.execute("ALTER TABLE chat_logs ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
        chunk_columns = [row["name"] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()]
        if "embedding" not in chunk_columns:
            conn.execute("ALTER TABLE chunks ADD COLUMN embedding TEXT")
        seed_embedding_models(conn)
        seed_auth_data(conn)
        ensure_config_file()
        count = conn.execute("SELECT COUNT(*) AS n FROM knowledge_bases WHERE deleted = 0").fetchone()["n"]
        if count == 0:
            seed_demo_data(conn)
        else:
            refresh_demo_index(conn)


def ensure_config_file() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    config = DEFAULT_SYSTEM_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                config.update(stored)
        except json.JSONDecodeError:
            pass
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def save_system_config(data: dict) -> dict:
    config = DEFAULT_SYSTEM_CONFIG.copy()
    config.update(data)
    config["chunkSize"] = max(80, min(2000, int(config.get("chunkSize") or DEFAULT_CHUNK_SIZE)))
    config["chunkOverlap"] = max(0, min(config["chunkSize"] - 1, int(config.get("chunkOverlap") or DEFAULT_CHUNK_OVERLAP)))
    config["defaultTopK"] = max(1, min(20, int(config.get("defaultTopK") or DEFAULT_TOP_K)))
    config["defaultThreshold"] = max(0.0, min(1.0, float(config.get("defaultThreshold") or DEFAULT_THRESHOLD)))
    config["minReliableScore"] = max(0.0, min(1.0, float(config.get("minReliableScore") or MIN_RELIABLE_SCORE)))
    config["maxAnswerChars"] = max(100, min(5000, int(config.get("maxAnswerChars") or 1200)))
    config["contextTurns"] = max(0, min(50, int(config.get("contextTurns") or DEFAULT_CONTEXT_TURNS)))
    config["contextMaxChars"] = max(0, min(20000, int(config.get("contextMaxChars") or 2000)))
    config["retrievalTimeoutSeconds"] = max(1, min(120, int(config.get("retrievalTimeoutSeconds") or 10)))
    config["answerTimeoutSeconds"] = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10)))
    config["maxUploadMb"] = max(1, min(200, int(config.get("maxUploadMb") or 20)))
    config["requestTimeoutSeconds"] = max(5, min(300, int(config.get("requestTimeoutSeconds") or 30)))
    config["responseCacheTtlSeconds"] = max(0, min(86400, int(config.get("responseCacheTtlSeconds") or 60)))
    config["vectorStorePath"] = str(config.get("vectorStorePath") or DB_PATH).strip()
    config["vectorCacheStrategy"] = str(config.get("vectorCacheStrategy") or "memory").strip()
    config["redisUrl"] = str(config.get("redisUrl") or "").strip()
    config["llmEnabled"] = bool(config.get("llmEnabled"))
    config["llmProvider"] = str(config.get("llmProvider") or "ollama").strip()
    if config["llmProvider"] not in {"ollama", "online"}:
        config["llmProvider"] = "ollama"
    config["answerMode"] = str(config.get("answerMode") or "enhanced").strip()
    if config["answerMode"] not in {"strict", "enhanced", "free"}:
        config["answerMode"] = "enhanced"
    config["ollamaUrl"] = str(config.get("ollamaUrl") or "http://127.0.0.1:11434").strip().rstrip("/")
    config["ollamaModel"] = str(config.get("ollamaModel") or "").strip()
    config["ollamaTemperature"] = max(0.0, min(1.5, float(config.get("ollamaTemperature") or 0.2)))
    config["onlineVendor"] = str(config.get("onlineVendor") or "").strip()
    config["onlineApiUrl"] = str(config.get("onlineApiUrl") or "").strip().rstrip("/")
    config["onlineApiKey"] = str(config.get("onlineApiKey") or "").strip()
    config["onlineModel"] = str(config.get("onlineModel") or "").strip()
    config["fallbackAnswer"] = str(config.get("fallbackAnswer") or DEFAULT_SYSTEM_CONFIG["fallbackAnswer"]).strip()
    config["sensitiveWords"] = str(config.get("sensitiveWords") or "").strip()
    config["refusalKeywords"] = str(config.get("refusalKeywords") or "").strip()
    config["refusalAnswer"] = str(config.get("refusalAnswer") or DEFAULT_SYSTEM_CONFIG["refusalAnswer"]).strip()
    config["dialogRules"] = str(config.get("dialogRules") or "").strip()
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def seed_embedding_models(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("SELECT name FROM embedding_models").fetchall()
    }
    for model in DEFAULT_EMBEDDING_MODELS:
        if model["name"] in existing:
            continue
        conn.execute(
            """
            INSERT INTO embedding_models
            (id, name, path, dimension, description, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                model["name"],
                model["path"],
                model["dimension"],
                model["description"],
                model["is_default"],
                now_ms(),
            ),
        )


def get_default_model_name(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT name FROM embedding_models WHERE is_default = 1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return row["name"] if row else "local-keyword-vector"


def seed_auth_data(conn: sqlite3.Connection) -> None:
    for name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        existing = conn.execute("SELECT id FROM roles WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE roles
                SET permissions = ?, builtin = 1
                WHERE id = ?
                """,
                (json.dumps(permissions, ensure_ascii=False), existing["id"]),
            )
            continue
        conn.execute(
            """
            INSERT INTO roles (id, name, description, permissions, builtin, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                name,
                f"系统预设角色：{name}",
                json.dumps(permissions, ensure_ascii=False),
                1,
                now_ms(),
            ),
        )


def auth_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return bool(row and row["n"] > 0)


def parse_json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item)]


def user_payload(row: sqlite3.Row) -> dict:
    permissions = normalize_permissions(row["permissions"])
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"] or row["username"],
        "avatarData": row["avatar_data"],
        "email": row["email"],
        "department": row["department"],
        "status": row["status"],
        "roleId": row["role_id"],
        "roleName": row["role_name"],
        "permissions": permissions,
        "allowedKbIds": parse_json_list(row["allowed_kb_ids"]),
        "failedAttempts": row["failed_attempts"],
        "lastLoginAt": row["last_login_at"],
        "createdAt": row["created_at"],
    }


def fetch_user_by_id(conn: sqlite3.Connection, user_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT u.*, r.name AS role_name, r.permissions
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    return user_payload(row) if row else None


def fetch_user_by_token(conn: sqlite3.Connection, token: str) -> dict | None:
    if not token:
        return None
    conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now_ms(),))
    row = conn.execute(
        """
        SELECT u.*, r.name AS role_name, r.permissions
        FROM auth_tokens t
        JOIN users u ON u.id = t.user_id
        JOIN roles r ON r.id = u.role_id
        WHERE t.token = ? AND t.expires_at > ? AND u.status = 'enabled'
        """,
        (token, now_ms()),
    ).fetchone()
    return user_payload(row) if row else None


def create_auth_token(conn: sqlite3.Connection, user_id: str, remember: bool = True) -> str:
    token = secrets.token_urlsafe(32)
    ttl = DEFAULT_TOKEN_TTL_SECONDS if remember else 8 * 60 * 60
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now_ms() + ttl * 1000, now_ms()),
    )
    return token


def kb_scope_ids(user: dict | None) -> list[str]:
    if not user:
        return []
    if "*" in user.get("permissions", []):
        return []
    return list(user.get("allowedKbIds") or [])


def can_access_kb(user: dict | None, kb_id: str | None) -> bool:
    if not user or not kb_id:
        return True
    if "*" in user.get("permissions", []):
        return True
    allowed = set(user.get("allowedKbIds") or [])
    return not allowed or kb_id in allowed


def restricted_kb_clause(user: dict | None, column: str) -> tuple[str, list[str]]:
    allowed = kb_scope_ids(user)
    if not allowed:
        return "", []
    return f"{column} IN ({','.join('?' for _ in allowed)})", allowed


def discover_local_models() -> list[dict]:
    discovered = []
    for directory in MODEL_DIRS:
        if not directory.exists():
            continue
        for item in directory.iterdir():
            if not item.is_dir():
                continue
            discovered.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "dimension": 0,
                    "description": "从本地模型目录发现，需在系统中确认维度后使用。",
                    "is_default": 0,
                }
            )
    return discovered


def seed_demo_data(conn: sqlite3.Connection) -> None:
    kb_id = str(uuid.uuid4())
    created = now_ms()
    conn.execute(
        """
        INSERT INTO knowledge_bases
        (id, name, description, category, department, owner, embedding_model, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kb_id,
            "王者荣耀客服知识库",
            "覆盖英雄玩法、账号安全、充值、活动和故障排查的演示知识库。",
            "账号问题",
            "客服运营部",
            "实训团队",
            "local-keyword-vector",
            "active",
            created,
        ),
    )
    doc_id = str(uuid.uuid4())
    text = "\n\n".join(
        [
            "实名认证修改：如账号实名信息存在错误，需进入腾讯成长守护平台或游戏内客服入口提交申诉。准备身份证明、账号信息和问题描述。审核期间请保持联系方式畅通。",
            "点券不到账：先确认支付平台扣款状态，再检查游戏内邮件和点券余额。若超过30分钟仍未到账，可提供订单号、区服、角色名和支付截图联系人工客服。",
            "英雄玩法：新手选择英雄时可优先练习亚瑟、妲己、后羿等操作门槛较低的英雄。对局中应关注小地图、兵线和团队集合信号。",
            "活动规则：活动奖励通常需要在活动页面手动领取。若任务已完成但奖励未到账，可重新登录游戏并检查活动时间、领取条件和背包容量。",
            "BUG反馈：遇到闪退、卡顿、结算异常或技能表现异常时，请记录发生时间、机型、系统版本、区服、角色名和复现步骤，便于技术人员定位。",
            "转人工客服：当问题涉及账号申诉、充值纠纷、处罚复核或机器人连续无法命中答案时，应转接人工，并同步最近对话内容。",
        ]
    )
    path = UPLOAD_DIR / f"{doc_id}.txt"
    path.write_text(text, encoding="utf-8")
    conn.execute(
        """
        INSERT INTO documents (id, kb_id, name, file_type, size, path, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, kb_id, "演示客服问答.txt", "txt", len(text.encode("utf-8")), str(path), "ready", created),
    )
    config = ensure_config_file()
    insert_chunks(conn, kb_id, doc_id, text, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, config)


def refresh_demo_index(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        """
        SELECT d.id, d.kb_id, d.path
        FROM documents d
        JOIN knowledge_bases k ON k.id = d.kb_id
        WHERE d.name = '演示客服问答.txt'
          AND k.name = '王者荣耀客服知识库'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return
    chunk_count = conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (row["id"],)).fetchone()["n"]
    if chunk_count >= 6:
        return
    path = Path(row["path"])
    if path.exists():
        config = ensure_config_file()
        insert_chunks(conn, row["kb_id"], row["id"], path.read_text(encoding="utf-8"), DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, config)


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def clean_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_answer_text(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*=+\s*([^=\n]+?)\s*=+\s*$", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*_=\s]{3,}\s*$", "", text)
    return text.replace("#", "")


def wants_markdown_output(question: str) -> bool:
    return bool(
        re.search(
            r"(markdown|md|表格|列表|分点|条目|标题|代码块|```|\|)",
            question,
            re.IGNORECASE,
        )
    )


def plain_dialogue_text(text: str) -> str:
    text = clean_answer_text(text)
    source = ""
    if "\n\n来源：" in text:
        text, source = text.split("\n\n来源：", 1)
        source = f"来源：{source.strip()}"
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.、)]\s+", "", text)
    text = re.sub(r"(?m)^\s*>+\s*", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\n{2,}", "\n", text)
    text = clean_text(text)
    text = re.sub(r"(\.{3}|…{1,2})$", "", text).rstrip()
    return f"{text}\n\n{source}" if source else text


def format_answer_for_question(question: str, answer: str) -> str:
    return clean_text(answer) if wants_markdown_output(question) else plain_dialogue_text(answer)


def explicit_query_hero(question: str) -> str:
    normalized = question
    for alias, canonical in HERO_ALIASES.items():
        normalized = normalized.replace(alias, canonical)
    names = [
        "韩信", "凯", "铠", "后羿", "鲁班七号", "孙尚香", "马可波罗", "狄仁杰", "李白", "赵云", "孙悟空",
        "澜", "镜", "兰陵王", "娜可露露", "露娜", "貂蝉", "妲己", "王昭君", "安琪拉", "诸葛亮", "小乔",
        "甄姬", "不知火舞", "亚瑟", "吕布", "程咬金", "夏侯惇", "花木兰", "关羽", "马超", "老夫子",
        "项羽", "张飞", "牛魔", "东皇太一", "蔡文姬", "瑶", "明世隐", "大乔", "孙膑",
    ]
    for name in sorted(names, key=len, reverse=True):
        if name in normalized:
            return "铠" if name == "凯" else name
    return ""


def normalize_hero_aliases(text: str) -> str:
    normalized = text
    for alias, canonical in HERO_ALIASES.items():
        normalized = normalized.replace(alias, canonical)
    return normalized


def remove_wrong_hero_heading(question: str, text: str) -> str:
    hero = explicit_query_hero(question)
    if not hero:
        return text
    return re.sub(rf"(?m)^英雄：(?!{re.escape(hero)}\s*$)[^\n\r]{{1,8}}\s*\n+", "", text)


def config_terms(value: str) -> list[str]:
    parts = re.split(r"[\n,，;；|]+", str(value or ""))
    return [part.strip() for part in parts if part.strip()]


def apply_sensitive_filter(text: str, config: dict) -> str:
    result = str(text or "")
    for word in sorted(config_terms(config.get("sensitiveWords", "")), key=len, reverse=True):
        result = re.sub(re.escape(word), "*" * max(1, len(word)), result, flags=re.IGNORECASE)
    return result


def match_refusal_answer(question: str, config: dict) -> str | None:
    lowered = question.lower()
    for word in config_terms(config.get("refusalKeywords", "")):
        if word.lower() in lowered:
            return str(config.get("refusalAnswer") or DEFAULT_SYSTEM_CONFIG["refusalAnswer"]).strip()
    return None


def match_dialog_rule_answer(question: str, config: dict) -> str | None:
    text = question.strip().lower()
    for line in str(config.get("dialogRules") or "").splitlines():
        if "=" not in line:
            continue
        raw_keys, answer = line.split("=", 1)
        answer = answer.strip()
        if not answer:
            continue
        keys = [item.strip().lower() for item in re.split(r"[|,，/、]+", raw_keys) if item.strip()]
        if any(key and key in text for key in keys):
            return answer
    return None


def trim_to_complete_text(text: str, max_chars: int) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    candidate = text[:max_chars].rstrip()
    min_pos = int(max_chars * 0.65)
    last_end = -1
    for mark in "。！？!?；;\n":
        pos = candidate.rfind(mark)
        if pos > last_end:
            last_end = pos
    if last_end >= min_pos:
        candidate = candidate[: last_end + 1].rstrip()
    return re.sub(r"(\.{3}|…{1,2})$", "", candidate).rstrip()


def ollama_json_request(base_url: str, path: str, payload: dict | None = None, timeout: int = 20) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def online_chat_url(config: dict) -> str:
    base_url = str(config.get("onlineApiUrl") or "").strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/chat/completions"


def online_chat_completion(prompt: str, config: dict, timeout: int) -> str:
    url = online_chat_url(config)
    api_key = str(config.get("onlineApiKey") or "").strip()
    model = str(config.get("onlineModel") or "").strip()
    if not url or not api_key or not model:
        return ""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": max(0.0, min(1.5, float(config.get("ollamaTemperature") or 0.2))),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return clean_answer_text(str(message.get("content") or choices[0].get("text") or "")).strip()


def resolve_ollama_model(config: dict, timeout: int) -> str:
    model = str(config.get("ollamaModel") or "").strip()
    if model:
        return model
    data = ollama_json_request(str(config.get("ollamaUrl") or "http://127.0.0.1:11434"), "/api/tags", None, timeout)
    models = data.get("models") or []
    return str(models[0].get("name") or "").strip() if models else ""


def build_compact_memory(
    question: str,
    client_context: list[dict],
    history: list[sqlite3.Row],
    max_chars: int = 900,
    max_messages: int = 8,
) -> str:
    current = clean_answer_text(question)
    items: list[dict] = []
    items.extend({"role": row["role"], "content": row["content"]} for row in reversed(history))
    items.extend(client_context)

    compact: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        role = str(item.get("role", "")).strip()
        if role not in {"user", "assistant"}:
            continue
        content = clean_answer_text(str(item.get("content", "")))
        if not content or content == current:
            continue
        content = content.split("\n\n来源：", 1)[0]
        content = re.sub(r"\s+", " ", content).strip()
        if role == "assistant" and len(content) > 220:
            content = trim_to_complete_text(content, 220)
        elif len(content) > 140:
            content = trim_to_complete_text(content, 140)
        key = (role, content)
        if key in seen:
            continue
        seen.add(key)
        compact.append({"role": role, "content": content})

    compact = compact[-max_messages:]
    lines = [
        f"{'用户' if item['role'] == 'user' else '助手'}：{item['content']}"
        for item in compact
    ]
    memory = "\n".join(lines)
    if len(memory) > max_chars:
        memory = memory[-max_chars:].lstrip()
    return memory


def build_llm_prompt(question: str, hits: list[dict], max_answer_chars: int, memory: str = "") -> str:
    context_blocks = []
    for index, hit in enumerate(hits[:4], 1):
        text = clean_answer_text(hit["text"])
        if len(text) > 650:
            text = text[:650].rstrip() + "（资料节选）"
        context_blocks.append(
            f"[资料{index}] 文档：{hit['document_name']}；知识库：{hit['kb_name']}；相似度：{hit['score']:.2f}\n{text}"
        )
    context = "\n\n".join(context_blocks)
    memory_block = (
        f"""历史对话记忆：
{memory}

"""
        if memory
        else ""
    )
    format_rule = (
        "用户明确要求格式化输出，可以按用户要求使用 Markdown、列表或表格。"
        if wants_markdown_output(question)
        else "用户没有要求 Markdown 时，必须用普通自然对话文本回答；不要使用 Markdown 标题、项目符号、编号列表、表格、加粗或代码块。"
    )
    return f"""你是王者荣耀客服知识库助手。请严格基于下方资料回答用户问题，不要使用资料外的事实，不要编造。

回答要求：
1. 先给直接结论，再给操作步骤或玩法要点。
2. 如果资料不足，明确说明资料不足，并建议换问法或转人工。
3. {format_rule}
4. 必须结合历史对话理解代词、简称、追问和用户已经问过的内容；如果历史与资料冲突，以资料为准。
5. 历史对话只用于理解上下文，不要在答案中输出“用户：”“助手：”这类角色标签，也不要复述历史问题。
6. 只回答用户这次问题直接相关的内容，不要整段搬运资料，不要加入用户没问的背景、免责声明或无关英雄/业务。
7. 答案要完整收尾，不要以省略号结尾；控制在 {max_answer_chars} 字以内。

用户问题：
{question}

{memory_block}
可用资料：
{context}
"""


def build_free_llm_prompt(question: str, max_answer_chars: int, memory: str = "") -> str:
    memory_block = (
        f"""历史对话记忆：
{memory}

"""
        if memory
        else ""
    )
    format_rule = (
        "用户明确要求格式化输出，可以按用户要求使用 Markdown、列表或表格。"
        if wants_markdown_output(question)
        else "用户没有要求 Markdown 时，必须用普通自然对话文本回答；不要使用 Markdown 标题、项目符号、编号列表、表格、加粗或代码块。"
    )
    return f"""你是王者荣耀客服助手。当前知识库没有可靠命中，但系统允许自由回答。

回答要求：
1. 可以根据通用知识和历史对话回答，但要自然克制，不要假装来自知识库。
2. 如果你不确定，要明确说不确定，并建议用户补充信息或切换知识库。
3. {format_rule}
4. 必须结合历史对话理解代词、简称和追问，但不要输出“用户：”“助手：”这类角色标签。
5. 只回答用户这次问题直接相关的内容，不要加入无关背景。
6. 答案要完整收尾，不要以省略号结尾；控制在 {max_answer_chars} 字以内。

用户问题：
{question}

{memory_block}"""


def generate_free_answer_with_ollama(
    question: str,
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    if not config.get("llmEnabled") or str(config.get("llmProvider") or "ollama") != "ollama":
        return fallback_answer, False
    try:
        timeout = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10)))
        base_url = str(config.get("ollamaUrl") or "http://127.0.0.1:11434").rstrip("/")
        model = resolve_ollama_model(config, timeout)
        if not model:
            return fallback_answer, False
        payload = {
            "model": model,
            "prompt": build_free_llm_prompt(question, max_answer_chars, memory),
            "stream": False,
            "options": {
                "temperature": max(0.0, min(1.5, float(config.get("ollamaTemperature") or 0.2))),
                "num_ctx": 4096,
            },
        }
        data = ollama_json_request(base_url, "/api/generate", payload, timeout)
        answer = clean_answer_text(str(data.get("response") or "")).strip()
        if not answer:
            return fallback_answer, False
        return trim_to_complete_text(answer, max_answer_chars), True
    except Exception:
        return fallback_answer, False


def generate_free_answer_with_online_api(
    question: str,
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    if not config.get("llmEnabled") or str(config.get("llmProvider") or "ollama") != "online":
        return fallback_answer, False
    try:
        timeout = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10)))
        prompt = build_free_llm_prompt(question, max_answer_chars, memory)
        answer = online_chat_completion(prompt, config, timeout)
        if not answer:
            return fallback_answer, False
        return trim_to_complete_text(answer, max_answer_chars), True
    except Exception:
        return fallback_answer, False


def generate_free_answer_with_llm(
    question: str,
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    provider = str(config.get("llmProvider") or "ollama")
    if provider == "online":
        return generate_free_answer_with_online_api(question, fallback_answer, config, max_answer_chars, memory)
    return generate_free_answer_with_ollama(question, fallback_answer, config, max_answer_chars, memory)


def generate_embedding(text: str, config: dict) -> list[float] | None:
    if not config.get("llmEnabled"):
        return None
    try:
        base_url = str(config.get("ollamaUrl") or "http://127.0.0.1:11434").rstrip("/")
        timeout = max(1, min(60, int(config.get("requestTimeoutSeconds") or 30)))
        payload = {"model": "nomic-embed-text", "prompt": text}
        data = ollama_json_request(base_url, "/api/embeddings", payload, timeout)
        embedding = data.get("embedding")
        if embedding and isinstance(embedding, list):
            return [float(x) for x in embedding]
        return None
    except Exception:
        return None


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if len(vec1) != len(vec2) or not vec1:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


def enhance_answer_with_ollama(
    question: str,
    hits: list[dict],
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    if not config.get("llmEnabled") or str(config.get("llmProvider") or "ollama") != "ollama" or not hits:
        return fallback_answer, False
    try:
        timeout = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10)))
        base_url = str(config.get("ollamaUrl") or "http://127.0.0.1:11434").rstrip("/")
        model = resolve_ollama_model(config, timeout)
        if not model:
            return fallback_answer, False
        payload = {
            "model": model,
            "prompt": build_llm_prompt(question, hits, max_answer_chars, memory),
            "stream": False,
            "options": {
                "temperature": max(0.0, min(1.5, float(config.get("ollamaTemperature") or 0.2))),
                "num_ctx": 4096,
            },
        }
        data = ollama_json_request(base_url, "/api/generate", payload, timeout)
        answer = clean_answer_text(str(data.get("response") or "")).strip()
        if not answer:
            return fallback_answer, False
        answer = trim_to_complete_text(answer, max_answer_chars)
        return answer, True
    except Exception:
        return fallback_answer, False


def enhance_answer_with_online_api(
    question: str,
    hits: list[dict],
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    if not config.get("llmEnabled") or str(config.get("llmProvider") or "ollama") != "online" or not hits:
        return fallback_answer, False
    try:
        timeout = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10)))
        prompt = build_llm_prompt(question, hits, max_answer_chars, memory)
        answer = online_chat_completion(prompt, config, timeout)
        if not answer:
            return fallback_answer, False
        return trim_to_complete_text(answer, max_answer_chars), True
    except Exception:
        return fallback_answer, False


def enhance_answer_with_llm(
    question: str,
    hits: list[dict],
    fallback_answer: str,
    config: dict,
    max_answer_chars: int,
    memory: str = "",
) -> tuple[str, bool]:
    provider = str(config.get("llmProvider") or "ollama")
    if provider == "online":
        return enhance_answer_with_online_api(question, hits, fallback_answer, config, max_answer_chars, memory)
    return enhance_answer_with_ollama(question, hits, fallback_answer, config, max_answer_chars, memory)


def extract_docx(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = []
    for paragraph in root.findall(".//w:body/w:p", ns):
        pieces = []
        for node in paragraph.iter():
            if node.tag == f"{{{ns['w']}}}t":
                pieces.append(node.text or "")
            elif node.tag == f"{{{ns['w']}}}tab":
                pieces.append("\t")
            elif node.tag == f"{{{ns['w']}}}br":
                pieces.append("\n")
        line = "".join(pieces).strip()
        if line:
            paragraphs.append(line)
    return clean_text("\n".join(paragraphs))


def extract_pdf(path: Path) -> str:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ValueError("当前环境未安装 PyPDF2，PDF 解析不可用；请上传 txt、md 或 docx。") from exc
    reader = PdfReader(str(path))
    return clean_text("\n".join(page.extract_text() or "" for page in reader.pages))


def extract_text(path: Path, file_type: str) -> str:
    if file_type in {"txt", "md"}:
        return clean_text(path.read_text(encoding="utf-8", errors="ignore"))
    if file_type == "docx":
        return extract_docx(path)
    if file_type == "pdf":
        return extract_pdf(path)
    raise ValueError("仅支持 txt、md、docx、pdf 文件。")


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current_hero = ""
    for paragraph in paragraphs:
        if re.fullmatch(r"[-*_=\s]{3,}", paragraph):
            continue
        hero_match = (
            re.match(r"^##\s*[一二三四五六七八九十]+、\s*([^（(\s#]+)", paragraph)
            or re.match(r"^#{2,6}\s*\d+[.、]\s*([^（(\s#，、]{1,8})", paragraph)
            or re.match(r"^英雄：([^\n\r]{1,8})", paragraph)
        )
        if hero_match:
            current_hero = hero_match.group(1).strip()
        prefix = f"英雄：{current_hero}\n" if current_hero and current_hero not in paragraph[:40] else ""
        if len(paragraph) <= chunk_size:
            chunks.append(prefix + paragraph)
            continue
        start = 0
        while start < len(paragraph):
            chunks.append(prefix + paragraph[start : start + chunk_size])
            start += max(1, chunk_size - chunk_overlap)
    return chunks


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_]+", lowered)
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    bigrams = ["".join(cjk[i : i + 2]) for i in range(max(0, len(cjk) - 1))]
    important = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
    return words + cjk + bigrams + important


def insert_chunks(
    conn: sqlite3.Connection,
    kb_id: str,
    doc_id: str,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    config: dict | None = None,
) -> None:
    old_rows = conn.execute("SELECT id FROM chunks WHERE doc_id = ?", (doc_id,)).fetchall()
    for row in old_rows:
        conn.execute("DELETE FROM vector_metadata WHERE chunk_id = ?", (row["id"],))
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    for index, chunk in enumerate(split_text(text, chunk_size, chunk_overlap)):
        tokens = json.dumps(tokenize(chunk), ensure_ascii=False)
        chunk_id = str(uuid.uuid4())
        embedding_json = None
        if config:
            embedding = generate_embedding(chunk, config)
            if embedding:
                embedding_json = json.dumps(embedding)
        conn.execute(
            """
            INSERT INTO chunks (id, kb_id, doc_id, chunk_index, text, tokens, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, kb_id, doc_id, index, chunk, tokens, embedding_json, now_ms()),
        )


def rebuild_document_vectors(conn: sqlite3.Connection, doc: sqlite3.Row, chunk_size: int, chunk_overlap: int, config: dict | None = None) -> int:
    path = Path(doc["path"])
    if not path.exists():
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", ("failed: 文件不存在", doc["id"]))
        return 0
    try:
        text = extract_text(path, doc["file_type"])
        if not text:
            raise ValueError("未解析到有效文本。")
        insert_chunks(conn, doc["kb_id"], doc["id"], text, chunk_size, chunk_overlap, config)
        conn.execute(
            "UPDATE documents SET size = ?, status = ? WHERE id = ?",
            (len(text.encode("utf-8")), "ready", doc["id"]),
        )
        return conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (doc["id"],)).fetchone()["n"]
    except Exception as exc:
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (f"failed: {exc}", doc["id"]))
        return 0


def score(query_tokens: list[str], chunk_tokens: list[str]) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    q = Counter(query_tokens)
    c = Counter(chunk_tokens)
    overlap = sum(min(q[token], c[token]) for token in q)
    density = overlap / math.sqrt(sum(q.values()) * sum(c.values()))
    keyword_bonus = min(0.35, sum(0.03 for token in set(q) if len(token) >= 2 and token in c))
    return round(min(1.0, density + keyword_bonus), 4)


def meaningful_query_terms(query: str) -> list[str]:
    stop_words = {
        "是什么",
        "什么",
        "怎么",
        "怎么玩",
        "如何",
        "有没有",
        "一下",
        "这个",
        "那个",
        "适合",
        "适合谁",
        "作用",
        "用法",
        "介绍",
        "推荐",
        "哪些",
        "可以",
        "为什么",
        "多少",
        "王者荣耀",
    }
    terms: set[str] = set()
    for token in tokenize(query):
        if len(token) >= 2 and token not in stop_words and not token.isdigit():
            terms.add(token)
    for piece in re.split(r"(是什么|有什么用|适合谁|怎么出|怎么用|怎么|如何|哪些|吗|呢|的|了|？|\?)", query):
        piece = piece.strip().lower()
        if 2 <= len(piece) <= 16 and piece not in stop_words:
            terms.add(piece)
    return sorted(terms, key=len, reverse=True)


def extract_catalog_names(rows: list[sqlite3.Row]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        text = row["text"]
        for match in re.finditer(r"【\d{1,4}】([^\n\r：:]{1,32})", text):
            name = match.group(1).strip()
            if not name:
                continue
            names.add(name)
            short_name = re.split(r"[（(]", name, 1)[0].strip()
            if short_name:
                names.add(short_name)
    return sorted(names, key=len, reverse=True)


def is_equipment_query(query: str, matched_catalog_names: list[str]) -> bool:
    if matched_catalog_names:
        return True
    return bool(
        re.search(
            r"(装备|出装|神装|道具|物品|基础属性|核心机制|适配英雄|适用分路|鞋|战刃|之刃|影刃|破晓|破军|"
            r"苍穹|逐日|名刀|末世|匕首|法杖|面具|圣杯|辉月|支配者|贤者|护甲|斗篷|征兆|魔女|"
            r"不死鸟|冰痕|庇护|打野刀)",
            query,
        )
    )


def is_equipment_row(row: sqlite3.Row | dict) -> bool:
    text = str(row["text"])
    kb_name = str(row["kb_name"])
    document_name = str(row["document_name"])
    return bool(
        re.search(r"(装备|道具|物品|基础库)", f"{kb_name} {document_name}")
        or re.search(r"(基础属性|核心机制|适用分路|适配英雄|版本定位)", text)
    )


def exact_heading_hit(term: str, text: str) -> bool:
    escaped = re.escape(term)
    return bool(
        re.search(rf"(?m)^\s*(?:[#]+\s*)?(?:【\d{{1,4}}】|\d+[.、])?\s*{escaped}(?:\s|$|[：:（(])", text)
    )


def token_similarity(left_tokens: list[str], right_tokens: list[str]) -> float:
    left = set(left_tokens)
    right = set(right_tokens)
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 4)


def normalize_tokens(tokens: list[str]) -> tuple[int, float, list[dict]]:
    counts = Counter(tokens)
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return 0, 0.0, []
    terms = [
        {"term": token, "weight": round(value / norm, 4)}
        for token, value in counts.most_common(12)
    ]
    return len(counts), round(norm, 4), terms


def has_clear_subject(question: str) -> bool:
    if explicit_query_hero(question):
        return True
    normalized = normalize_hero_aliases(question.strip())
    if re.search(r"(射手|法师|刺客|战士|坦克|辅助|游走|打野|中路|对抗路|发育路|装备|知识库)", normalized):
        return True
    action_pattern = r"(具体|详细|继续|然后|还有|上面|刚才|这个|那个|该|它|他|她|怎么玩|怎么打|怎么出装|怎么用|有什么用|打法|玩法|出装|铭文|连招|克制|反制|适合|适合谁|用法)"
    stripped = re.sub(action_pattern, "", normalized)
    stripped = re.sub(r"[吗呢啊呀吧的了么怎谁那再点说？?，,\s]", "", stripped)
    if not stripped:
        return False
    terms = [term for term in meaningful_query_terms(normalized) if not re.search(action_pattern, term)]
    return any(len(term) >= 2 for term in terms)


def is_contextual_followup(question: str) -> bool:
    normalized = normalize_hero_aliases(re.sub(r"\s+", "", question.strip()))
    if not normalized:
        return False
    if re.search(r"(这个|那个|该|它|他|她|上面|刚才|上一|前面|继续|接着|还有|再说|然后|那|具体|详细|展开|细说|多说)", normalized):
        return True
    if len(normalized) <= 12 and re.search(r"(怎么玩|怎么打|怎么出装|怎么用|连招|铭文|出装|打法|玩法|克制|反制|适合谁)", normalized):
        return not has_clear_subject(normalized)
    return False


def should_use_history(question: str) -> bool:
    return is_contextual_followup(question)


def normalize_client_context(value: object, limit: int = 20) -> list[dict]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = clean_answer_text(str(item.get("content", "")))[:1000]
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def extract_topic_from_text(text: str) -> str:
    text = clean_answer_text(text)
    hero = explicit_query_hero(text)
    if hero:
        return hero
    if len(re.sub(r"\s+", "", text)) <= 20 and is_contextual_followup(text):
        return ""
    for pattern in [
        r"【\d{1,4}】([^\n\r：:]{1,32})",
        r"(?:关于|围绕|针对)([^，。！？\n\r]{2,16})",
        r"^([^，。！？\n\r]{2,16})(?:是|属于|适合|可以|的)",
    ]:
        match = re.search(pattern, text)
        if match:
            topic = re.split(r"[（(]", match.group(1).strip(), 1)[0].strip()
            if 2 <= len(topic) <= 16:
                return topic
    terms = meaningful_query_terms(text[:120])
    for term in terms:
        if 2 <= len(term) <= 12 and not re.search(r"(来源|相似度|问题|回答|玩法|打法|具体|详细)", term):
            return term
    return ""


def infer_context_topic(question: str, client_context: list[dict], history: list[sqlite3.Row]) -> str:
    current = clean_answer_text(question)
    candidates: list[dict] = []
    candidates.extend(client_context)
    candidates.extend({"role": row["role"], "content": row["content"]} for row in reversed(history))

    user_candidates = [
        item for item in reversed(candidates)
        if (
            item.get("role") == "user"
            and clean_answer_text(item.get("content", "")) != current
            and not is_contextual_followup(str(item.get("content", "")))
            and has_clear_subject(str(item.get("content", "")))
        )
    ]
    assistant_candidates = [
        item for item in reversed(candidates)
        if item.get("role") == "assistant" and clean_answer_text(item.get("content", "")) != current
    ]
    for item in user_candidates + assistant_candidates:
        topic = extract_topic_from_text(str(item.get("content", "")))
        if topic:
            return topic
    return ""


def infer_context_intent(question: str, client_context: list[dict], history: list[sqlite3.Row]) -> str:
    current = clean_answer_text(question)
    candidates: list[dict] = []
    candidates.extend(client_context)
    candidates.extend({"role": row["role"], "content": row["content"]} for row in reversed(history))
    for item in reversed(candidates):
        if item.get("role") != "user":
            continue
        content = clean_answer_text(str(item.get("content", "")))
        if not content or content == current or is_contextual_followup(content):
            continue
        if re.search(r"(克制|被克制|反制|counter)", content, re.IGNORECASE):
            return "克制关系"
        if re.search(r"(连招|技能连招|抓人连招|刷野连招)", content):
            return "连招"
        if re.search(r"(出装|装备|神装|铭文)", content):
            return "出装铭文"
        if re.search(r"(怎么玩|玩法|攻略|思路|打法|运营|对线|团战)", content):
            return "怎么玩"
        if re.search(r"(适合谁|有什么用|怎么用|是什么)", content):
            return "用法"
    return ""


def ordered_user_questions(current_question: str, client_context: list[dict], history: list[sqlite3.Row]) -> list[str]:
    current = clean_answer_text(current_question)
    items: list[dict] = []
    items.extend({"role": row["role"], "content": row["content"]} for row in reversed(history))
    items.extend(client_context)
    questions: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item.get("role") != "user":
            continue
        content = clean_answer_text(str(item.get("content", "")))
        if not content or content == current or content in seen:
            continue
        seen.add(content)
        questions.append(content)
    return questions


def ordered_dialog_items(current_question: str, client_context: list[dict], history: list[sqlite3.Row]) -> list[dict]:
    current = clean_answer_text(current_question)
    items: list[dict] = []
    items.extend({"role": row["role"], "content": row["content"]} for row in reversed(history))
    items.extend(client_context)
    ordered: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        role = str(item.get("role", "")).strip()
        content = clean_answer_text(str(item.get("content", "")))
        if role not in {"user", "assistant"} or not content or content == current:
            continue
        key = (role, content)
        if key in seen:
            continue
        seen.add(key)
        ordered.append({"role": role, "content": content})
    return ordered


def resolve_contextual_history_question(question: str, items_before: list[dict]) -> str:
    if not is_contextual_followup(question):
        return question
    topic = infer_context_topic(question, items_before, [])
    if not topic:
        return question
    if not re.search(r"(怎么玩|怎么打|怎么出装|怎么用|有什么用|连招|铭文|出装|打法|玩法|克制|反制|适合谁)", question):
        intent = infer_context_intent(question, items_before, [])
        if intent:
            return f"{topic} {intent} {question}"
    return f"{topic} {question}"


def chinese_ordinal_index(text: str) -> int | None:
    if re.search(r"(第一次|第一个|第一条|第一句|最开始|一开始|开头|最初)", text):
        return 0
    if re.search(r"(第二次|第二个|第二条|第二句)", text):
        return 1
    if re.search(r"(第三次|第三个|第三条|第三句)", text):
        return 2
    if re.search(r"(第四次|第四个|第四条|第四句)", text):
        return 3
    if re.search(r"(第五次|第五个|第五条|第五句)", text):
        return 4
    match = re.search(r"第\s*(\d+)\s*(?:次|个|条|句|轮|问|题)", text)
    if match:
        return max(0, int(match.group(1)) - 1)
    return None


def resolve_referenced_question(question: str, client_context: list[dict], history: list[sqlite3.Row]) -> str:
    normalized = re.sub(r"\s+", "", question)
    wants_repeat = bool(re.search(r"(再回答|重新回答|重答|再说一遍|重复|回到|回答一遍|说一遍|展开)", normalized))
    asks_question_ref = bool(re.search(r"(问题|提问|问的|问过|那条|那句|那个|这条|这句)", normalized))
    if not (wants_repeat or asks_question_ref):
        return ""
    dialog_items = ordered_dialog_items(question, client_context, history)
    questions = [item["content"] for item in dialog_items if item["role"] == "user"]
    if not questions:
        return ""
    ordinal = chinese_ordinal_index(normalized)
    target = ""
    if ordinal is not None:
        target = questions[ordinal] if ordinal < len(questions) else ""
    elif re.search(r"(上一个|上一条|上一句|上一轮|刚才|前一个|前面那个|上面那个)", normalized):
        target = questions[-1]
    if not target:
        return ""
    target_pos = next(
        (index for index, item in enumerate(dialog_items) if item["role"] == "user" and item["content"] == target),
        -1,
    )
    return resolve_contextual_history_question(target, dialog_items[:target_pos]) if target_pos >= 0 else target


def is_history_meta_question(question: str) -> bool:
    normalized = re.sub(r"\s+", "", clean_answer_text(question))
    if not normalized:
        return False
    if not re.search(r"(什么|哪个|哪些|哪一个|第几)", normalized):
        return False
    return bool(
        re.search(r"(刚开始|一开始|最开始|第一次|第一个|开头|最初).{0,10}(问|提问|问题)", normalized)
        or re.search(r"(我|我们|咱).{0,8}(刚开始|一开始|最开始|第一次|第一个|开头|最初).{0,10}(问|提问|问题)", normalized)
        or re.search(r"(最后|最近|上一个|上一条|前一个|前面|刚才).{0,10}(问|提问|问题)", normalized)
        or re.search(r"(我|我们|咱).{0,8}(最后|最近|上一个|上一条|前一个|前面|刚才).{0,10}(问|提问|问题)", normalized)
        or re.search(r"(我|我们|咱).{0,8}(问过|提过|说过|聊过).{0,8}(什么|哪些)", normalized)
    )


def non_meta_questions(questions: list[str]) -> list[str]:
    filtered = [item for item in questions if not is_history_meta_question(item)]
    return filtered or questions


def resolve_history_meta_answer(question: str, client_context: list[dict], history: list[sqlite3.Row]) -> str | None:
    if not is_history_meta_question(question):
        return None
    questions = ordered_user_questions(question, client_context, history)
    if not questions:
        return "我还没有看到你之前的问题。"
    normalized = re.sub(r"\s+", "", clean_answer_text(question))
    useful_questions = non_meta_questions(questions)
    ordinal = chinese_ordinal_index(normalized)
    if ordinal is not None:
        if ordinal < len(useful_questions):
            prefix = "刚开始" if ordinal == 0 else f"第 {ordinal + 1} 个"
            return f"你{prefix}问的是：{useful_questions[ordinal]}。"
        return f"我目前只看到 {len(useful_questions)} 个有效问题，还没有第 {ordinal + 1} 个。"
    if re.search(r"(刚开始|一开始|最开始|第一次|第一个|开头|最初)", normalized):
        return f"你刚开始问的是：{useful_questions[0]}。"
    if re.search(r"(最后|最近|上一个|上一条|前一个|前面|刚才)", normalized):
        return f"你最近一个有效问题是：{useful_questions[-1]}。"
    if len(useful_questions) == 1:
        return f"你问过的问题是：{useful_questions[0]}。"
    preview = "；".join(useful_questions[-5:])
    return f"你最近问过这些问题：{preview}。"


def answer_greeting(question: str) -> str | None:
    normalized = re.sub(r"\s+", "", clean_answer_text(question)).lower()
    if not normalized:
        return None
    game_terms = r"(怎么玩|怎么打|怎么出装|出装|铭文|连招|克制|反制|装备|知识库|上传|删除|登录|账号|韩信|铠|凯|后羿)"
    if re.search(game_terms, normalized):
        return None
    if normalized in {"你好", "您好", "你好啊", "您好啊", "你好嘛", "你好吗", "在吗", "在不在", "嗨", "hi", "hello"}:
        return "我在。你可以继续问英雄玩法、出装、克制关系，或者知识库里的具体内容。"
    if len(normalized) <= 8 and re.search(r"(你好|您好|在吗|嗨|hello|hi)", normalized):
        return "我在。你可以继续问英雄玩法、出装、克制关系，或者知识库里的具体内容。"
    return None


def should_skip_kb_retrieval(question: str) -> str:
    normalized = re.sub(r"\s+", "", clean_answer_text(question)).lower()
    if not normalized:
        return "空问题"
    if answer_greeting(question):
        return "普通问候不需要知识库检索"
    if normalized in {"谢谢", "谢谢你", "感谢", "感谢你", "好的", "好", "嗯", "哦", "知道了", "明白了", "ok", "okay"}:
        return "普通寒暄不需要知识库检索"
    if len(normalized) <= 2 and not explicit_query_hero(normalized):
        return "问题过短，缺少明确检索意图"
    return ""


def rewrite_contextual_question(question: str, client_context: list[dict], history: list[sqlite3.Row]) -> str:
    referenced_question = resolve_referenced_question(question, client_context, history)
    if referenced_question:
        return referenced_question
    if not is_contextual_followup(question):
        return question
    topic = infer_context_topic(question, client_context, history)
    if not topic or topic in question:
        return question
    if not re.search(r"(怎么玩|怎么打|怎么出装|怎么用|有什么用|连招|铭文|出装|打法|玩法|克制|反制|适合谁)", question):
        intent = infer_context_intent(question, client_context, history)
        if intent:
            return f"{topic} {intent} {question}"
    return f"{topic} {question}"


def extract_query_heroes(query: str, rows: list[sqlite3.Row]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        for match in re.finditer(r"英雄：([^\n\r]{1,8})", row["text"]):
            names.add(match.group(1).strip())
        for match in re.finditer(r"^##\s*[一二三四五六七八九十]+、\s*([^（(\s#]+)", row["text"], re.MULTILINE):
            names.add(match.group(1).strip())
        for match in re.finditer(r"(?m)^([^\s：:（）()#，、]{1,8})\s*\n\s*克制英雄：", row["text"]):
            names.add(match.group(1).strip())
    normalized_query = query
    for alias, canonical in HERO_ALIASES.items():
        normalized_query = normalized_query.replace(alias, canonical)
    return [name for name in sorted(names, key=len, reverse=True) if name and name in normalized_query]


def search_chunks(conn: sqlite3.Connection, query: str, kb_id: str | None, top_k: int, config: dict | None = None) -> list[dict]:
    query_tokens = tokenize(query)
    query_text = query.strip()
    params: tuple = ()
    where = "WHERE k.deleted = 0"
    if kb_id:
        where = "WHERE c.kb_id = ? AND k.deleted = 0"
        params = (kb_id,)
    rows = conn.execute(
        f"""
        SELECT c.*, d.name AS document_name, k.name AS kb_name
        FROM chunks c
        JOIN documents d ON d.id = c.doc_id
        JOIN knowledge_bases k ON k.id = c.kb_id
        {where}
        """,
        params,
    ).fetchall()
    
    # 尝试使用 embedding 向量检索
    query_embedding = None
    if config:
        query_embedding = generate_embedding(query_text, config)
    
    if query_embedding:
        # 使用向量检索
        results = []
        for row in rows:
            embedding_json = row["embedding"]
            if not embedding_json:
                continue
            try:
                chunk_embedding = json.loads(embedding_json)
                similarity = cosine_similarity(query_embedding, chunk_embedding)
                if similarity > 0.3:
                    item = row_to_dict(row)
                    item["score"] = round(max(0.0, min(1.0, similarity)), 4)
                    results.append(item)
            except (json.JSONDecodeError, ValueError):
                continue
        results.sort(key=lambda item: item["score"], reverse=True)
        if results:
            return results[:top_k]
    
    # 降级到关键词匹配
    query_heroes = extract_query_heroes(query_text, rows)
    catalog_names = extract_catalog_names(rows)
    matched_catalog_names = [name for name in catalog_names if name and name.lower() in query_text.lower()]
    equipment_query = is_equipment_query(query_text, matched_catalog_names)
    query_terms = meaningful_query_terms(query_text)
    counter_query = bool(re.search(r"(克制|被克制|反制|counter)", query_text, re.IGNORECASE))
    build_query = bool(re.search(r"(出装|装备|神装|铭文)", query_text))
    combo_query = bool(re.search(r"(连招|技能连招|抓人连招|刷野连招)", query_text))
    gameplay_query = bool(re.search(r"(怎么玩|玩法|攻略|思路|打法|运营|对线|团战|具体|详细)", query_text))
    role_match = re.search(r"(射手|法师|刺客|战士|坦克|辅助|游走|打野|中路|对抗路|发育路)", query_text)
    role_query = role_match.group(1) if role_match else ""
    ranked = []
    for row in rows:
        text = row["text"]
        hero_in_text = any(hero in text for hero in query_heroes)
        if query_heroes and not equipment_query and not hero_in_text:
            continue
        value = score(query_tokens, json.loads(row["tokens"]))
        if query_heroes and (not equipment_query or hero_in_text):
            value = max(value, 0.18)
        row_is_equipment = is_equipment_row(row)
        text_l = text.lower()
        scope_l = f"{row['kb_name']} {row['document_name']}".lower()
        for term in query_terms[:8]:
            term_l = term.lower()
            if term_l in text_l:
                value += 0.08 if len(term_l) >= 3 else 0.05
            if exact_heading_hit(term, text):
                value += 0.12
            if term_l in scope_l:
                value += 0.12
        for name in matched_catalog_names[:3]:
            if name in text:
                value += 0.22
            if re.search(rf"【\d{{1,4}}】\s*{re.escape(name)}(?:\s|$|[：:（(])", text):
                value += 0.2
        if equipment_query:
            if row_is_equipment and (not query_heroes or hero_in_text or matched_catalog_names):
                value += 0.18
                if re.search(r"(基础属性|核心机制|适用分路|适配英雄|版本定位)", text):
                    value += 0.08
            elif not query_heroes and re.search(r"(铭文推荐|搭配逻辑)", text):
                value -= 0.08
        if gameplay_query:
            if re.search(r"(定位|核心特点|运营思路|打法|使用技巧|连招|刷野|团战|对线)", text):
                value += 0.12
            if re.search(r"(###\s*1\.\s*英雄定位|定位为)", text):
                value += 0.12
            if re.search(r"(铭文|出装)", text) and not re.search(r"(铭文|出装)", query_text):
                value -= 0.08
            if not counter_query and ("克制" in row["kb_name"] or "克制" in row["document_name"] or re.search(r"(克制英雄|被克制英雄)", text)):
                value -= 0.24
            if not build_query and row_is_equipment:
                value -= 0.14
            if "英雄攻略" in row["kb_name"] or re.search(r"(英雄定位|核心特点|技能深度解析|野区/边路运营|团战打法|核心连招)", text):
                value += 0.18
            if role_query:
                if re.search(rf"(?:[（(][^）)]*{re.escape(role_query)}|定位[^。\n\r]{{0,12}}{re.escape(role_query)}|主流分路[^。\n\r]{{0,12}}{re.escape(role_query)})", text[:220]):
                    value += 0.22
                elif re.search(r"(?:[（(][^）)]*(射手|法师|刺客|战士|坦克|辅助)|官方定位)", text[:220]):
                    value -= 0.08
        if combo_query:
            if re.search(r"(核心连招|连招技巧|基础刷野连招|抓人连招|团战连招|技能衔接)", text):
                value += 0.28
            elif not counter_query:
                value -= 0.08
            if not counter_query and ("克制" in row["kb_name"] or "克制" in row["document_name"] or re.search(r"(克制英雄|被克制英雄)", text)):
                value -= 0.3
        if build_query:
            if "英雄出装" in row["kb_name"] or re.search(r"(出装顺序|出装逻辑|铭文搭配|装备)", text):
                value += 0.22
            if not counter_query and ("克制" in row["kb_name"] or "克制" in row["document_name"]):
                value -= 0.18
        if counter_query:
            if "克制" in row["kb_name"] or "克制" in row["document_name"]:
                value += 0.25
            if re.search(r"(克制英雄|被克制英雄)", text):
                value += 0.12
            if query_heroes and any(hero in text for hero in query_heroes):
                value += 0.12
            for hero in query_heroes:
                if re.search(rf"(?m)^{re.escape(hero)}\s*\n\s*克制英雄：", text):
                    value += 0.3
        value = round(max(0.0, min(1.0, value)), 4)
        if value > 0:
            item = row_to_dict(row)
            item["score"] = value
            ranked.append(item)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def search_chunks_for_user(
    conn: sqlite3.Connection,
    query: str,
    kb_id: str | None,
    top_k: int,
    user: dict | None,
    config: dict | None = None,
) -> list[dict]:
    if kb_id:
        if not can_access_kb(user, kb_id):
            return []
        return search_chunks(conn, query, kb_id, top_k, config)
    allowed = kb_scope_ids(user)
    if not allowed:
        return search_chunks(conn, query, None, top_k, config)
    hits: list[dict] = []
    for scoped_kb_id in allowed:
        hits.extend(search_chunks(conn, query, scoped_kb_id, top_k, config))
    hits.sort(key=lambda item: item["score"], reverse=True)
    return hits[:top_k]


def focus_hits_for_question(question: str, hits: list[dict]) -> list[dict]:
    focused = list(hits)
    catalog_names = extract_catalog_names(focused)
    matched_catalog_names = [name for name in catalog_names if name and name.lower() in question.lower()]
    if is_equipment_query(question, matched_catalog_names):
        equipment_hits = [hit for hit in focused if is_equipment_row(hit)]
        if equipment_hits:
            focused = equipment_hits
        if matched_catalog_names:
            exact_hits = [hit for hit in focused if any(name in hit["text"] for name in matched_catalog_names)]
            if exact_hits:
                focused = exact_hits
    target_heroes = extract_query_heroes(question, focused)
    explicit_hero = explicit_query_hero(question)
    if explicit_hero and explicit_hero not in target_heroes:
        target_heroes.append(explicit_hero)
    if target_heroes:
        hero_hits = [hit for hit in focused if any(hero in hit["text"] for hero in target_heroes)]
        if hero_hits:
            focused = hero_hits
    return focused


def build_answer(
    question: str,
    hits: list[dict],
    threshold: float,
    max_answer_chars: int = 1200,
    fallback_answer: str = DEFAULT_SYSTEM_CONFIG["fallbackAnswer"],
) -> tuple[str, list[dict], float]:
    threshold = max(threshold, MIN_RELIABLE_SCORE)
    if question.strip() in {"人工", "转人工", "人工客服"} or "转人工" in question:
        return (
            "已为你触发人工客服转接。请补充区服、角色名、问题发生时间和相关截图，人工坐席会结合当前对话继续处理。",
            [],
            0.0,
        )
    if not hits or hits[0]["score"] < threshold:
        return (
            fallback_answer,
            [],
            hits[0]["score"] if hits else 0.0,
        )
    hits = focus_hits_for_question(question, hits)
    strong_hits = [hit for hit in hits if hit["score"] >= threshold]
    if not strong_hits:
        return (
            fallback_answer,
            [],
            hits[0]["score"] if hits else 0.0,
        )
    source_lines = []
    for hit in strong_hits[:4]:
        source_lines.append(hit["text"])
    answer = clean_answer_text(remove_wrong_hero_heading(question, "\n\n".join(source_lines)))
    answer = trim_to_complete_text(answer, max_answer_chars)
    answer = f"{answer}\n\n来源：{strong_hits[0]['document_name']}；相似度 {strong_hits[0]['score']:.2f}"
    answer = format_answer_for_question(question, answer)
    sources = [
        {
            "document": hit["document_name"],
            "knowledgeBase": hit["kb_name"],
            "score": hit["score"],
            "snippet": clean_answer_text(hit["text"])[:160],
        }
        for hit in strong_hits
    ]
    return answer, sources, strong_hits[0]["score"]


def serialize_hit(hit: dict, limit: int = 220) -> dict:
    return {
        "chunkId": hit.get("id", ""),
        "chunkIndex": hit.get("chunk_index", 0),
        "document": hit.get("document_name", ""),
        "knowledgeBase": hit.get("kb_name", ""),
        "score": round(float(hit.get("score") or 0), 4),
        "snippet": clean_answer_text(str(hit.get("text") or ""))[:limit],
    }


def build_retrieval_debug(
    question: str,
    effective_question: str,
    search_query: str,
    kb_id: str | None,
    hits: list[dict],
    threshold: float,
    reliable_threshold: float,
    answer_mode: str,
    llm_enhanced: bool = False,
    answer_source: str = "knowledge",
) -> dict:
    best_score = float(hits[0]["score"]) if hits else 0.0
    if not hits:
        status = "未召回任何文本块"
    elif best_score < reliable_threshold:
        status = "有召回，但最高分低于可靠阈值"
    else:
        status = "已命中可靠知识库内容"
    return {
        "question": question,
        "effectiveQuestion": effective_question,
        "searchQuery": search_query,
        "kbId": kb_id or "",
        "answerMode": answer_mode,
        "threshold": round(float(threshold), 4),
        "reliableThreshold": round(float(reliable_threshold), 4),
        "bestScore": round(best_score, 4),
        "status": status,
        "answerSource": answer_source,
        "llmEnhanced": bool(llm_enhanced),
        "hits": [serialize_hit(hit) for hit in hits[:8]],
    }


# ── Flask 应用初始化 ──────────────────────────────────────────────
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

# 存储当前请求的用户信息（Flask 使用 g 对象替代实例变量）
from flask import g as flask_g


def _bearer_token() -> str:
    """从 Authorization 头提取 Bearer token"""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return ""


def _get_current_user() -> dict | None:
    """获取当前登录用户"""
    if not hasattr(flask_g, "_user"):
        flask_g._user = None
        token = _bearer_token()
        if token:
            with connect() as conn:
                flask_g._user = fetch_user_by_token(conn, token)
    return flask_g._user


def _required_permission(path: str, method: str) -> str | None:
    """根据路由匹配所需权限"""
    for route_method, pattern, permission in ROUTE_PERMISSIONS:
        if route_method == method and pattern.match(path):
            return permission
    return None


def _authorize(required_permission: str | None = None) -> dict | None:
    """鉴权装饰器核心逻辑，返回用户信息或抛出异常"""
    user = _get_current_user()
    if required_permission and not has_permission(user or {}, required_permission):
        if not user:
            from flask import abort
            resp = jsonify({"error": "请先登录。", "authRequired": True})
            resp.status_code = 401
            raise _HTTPException(resp)
        resp = jsonify({"error": "当前账号没有该操作权限。"})
        resp.status_code = 403
        raise _HTTPException(resp)
    return user


class _HTTPException(Exception):
    """自定义 HTTP 异常，携带 Response 对象"""
    def __init__(self, response):
        self.response = response


@app.errorhandler(_HTTPException)
def handle_http_exception(e):
    return e.response


# ── 根路由与静态文件 ──────────────────────────────────────────────
@app.route("/")
def index():
    return redirect("/static/login.html")


# ── 认证相关路由（无需鉴权）────────────────────────────────────────
@app.route("/api/auth/status", methods=["GET"])
def api_auth_status():
    with connect() as conn:
        initialized = auth_initialized(conn)
    return jsonify({"initialized": initialized})


@app.route("/api/auth/setup", methods=["POST"])
def api_auth_setup():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    email = str(data.get("email", "")).strip()
    if not username or len(password) < 6:
        return jsonify({"error": "管理员账号不能为空，密码至少 6 位。"}), 400
    with connect() as conn:
        if auth_initialized(conn):
            return jsonify({"error": "系统已完成初始化，请直接登录。"}), 400
        role = conn.execute("SELECT id FROM roles WHERE name = ?", ("超级管理员",)).fetchone()
        if not role:
            seed_auth_data(conn)
            role = conn.execute("SELECT id FROM roles WHERE name = ?", ("超级管理员",)).fetchone()
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users
            (id, username, password_hash, email, department, status, role_id, allowed_kb_ids, failed_attempts, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, hash_password(password), email, "系统管理部", "enabled", role["id"], "[]", 0, now_ms()),
        )
        token = create_auth_token(conn, user_id, True)
        user = fetch_user_by_id(conn, user_id)
    return jsonify({"token": token, "user": user}), 201


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    email = str(data.get("email", "")).strip()
    remember = bool(data.get("remember", True))
    if not username or len(password) < 6:
        return jsonify({"error": "用户名不能为空，密码至少 6 位。"}), 400
    with connect() as conn:
        if not auth_initialized(conn):
            return jsonify({"error": "请先完成超级管理员初始化。"}), 400
        role = conn.execute("SELECT id FROM roles WHERE name = ?", ("普通用户",)).fetchone()
        if not role:
            seed_auth_data(conn)
            role = conn.execute("SELECT id FROM roles WHERE name = ?", ("普通用户",)).fetchone()
        user_id = str(uuid.uuid4())
        try:
            conn.execute(
                """
                INSERT INTO users
                (id, username, password_hash, email, department, status, role_id, allowed_kb_ids, failed_attempts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, hash_password(password), email, "普通用户", "enabled", role["id"], "[]", 0, now_ms()),
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "用户名已存在。"}), 400
        token = create_auth_token(conn, user_id, remember)
        user = fetch_user_by_id(conn, user_id)
    return jsonify({"token": token, "user": user}), 201


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role_name = str(data.get("roleName", "")).strip()
    remember = bool(data.get("remember", True))
    with connect() as conn:
        row = conn.execute(
            """
            SELECT u.*, r.name AS role_name, r.permissions
            FROM users u JOIN roles r ON r.id = u.role_id
            WHERE u.username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return jsonify({"error": "账号或密码错误。"}), 401
        if row["status"] != "enabled":
            return jsonify({"error": "账号已禁用。"}), 403
        if row["failed_attempts"] >= MAX_LOGIN_FAILURES:
            return jsonify({"error": "登录失败次数过多，请联系管理员重置状态。"}), 403
        if not verify_password(password, row["password_hash"]):
            conn.execute("UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id = ?", (row["id"],))
            return jsonify({"error": "账号或密码错误。"}), 401
        if role_name and row["role_name"] != role_name:
            return jsonify({"error": f"该账号不是{role_name}，请选择正确身份登录。"}), 403
        conn.execute("UPDATE users SET failed_attempts = 0, last_login_at = ? WHERE id = ?", (now_ms(), row["id"]))
        token = create_auth_token(conn, row["id"], remember)
        user = fetch_user_by_id(conn, row["id"])
    return jsonify({"token": token, "user": user})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    token = _bearer_token()
    if token:
        with connect() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
    return jsonify({"ok": True})


# ── 需要鉴权的 API 路由 ────────────────────────────────────────────
@app.route("/api/me", methods=["GET"])
def api_me_get():
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    return jsonify({"user": user})


@app.route("/api/me", methods=["PUT"])
def api_me_put():
    perm = _required_permission(request.path, "PUT")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    display_name = str(data.get("displayName", "")).strip()
    avatar_data = str(data.get("avatarData", "")).strip()
    if not display_name or len(display_name) > 30:
        return jsonify({"error": "名称不能为空，且不能超过 30 个字符。"}), 400
    if avatar_data:
        if len(avatar_data) > MAX_AVATAR_DATA_CHARS:
            return jsonify({"error": "头像图片过大，请选择 500KB 以内的图片。"}), 400
        if not re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=]+$", avatar_data):
            return jsonify({"error": "头像仅支持 png、jpg、webp 或 gif 图片。"}), 400
    with connect() as conn:
        conn.execute("UPDATE users SET display_name = ?, avatar_data = ? WHERE id = ?", (display_name, avatar_data, user["id"]))
        updated = fetch_user_by_id(conn, user["id"])
    return jsonify({"user": updated})


@app.route("/api/permissions/catalog", methods=["GET"])
def api_permissions_catalog():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    return jsonify(PERMISSION_CATALOG)


@app.route("/api/users", methods=["GET"])
def api_users_list():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    keyword = (request.args.get("q") or "").strip()
    department = (request.args.get("department") or "").strip()
    clauses = ["1 = 1"]
    args: list = []
    if keyword:
        clauses.append("(u.username LIKE ? OR u.email LIKE ?)")
        args.extend([f"%{keyword}%", f"%{keyword}%"])
    if department:
        clauses.append("u.department LIKE ?")
        args.append(f"%{department}%")
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT u.*, r.name AS role_name, r.permissions
            FROM users u JOIN roles r ON r.id = u.role_id
            WHERE {" AND ".join(clauses)}
            ORDER BY u.created_at DESC
            """,
            tuple(args),
        ).fetchall()
    return jsonify([user_payload(row) for row in rows])


@app.route("/api/users", methods=["POST"])
def api_users_create():
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role_id = str(data.get("roleId", "")).strip()
    if not username or len(password) < 6 or not role_id:
        return jsonify({"error": "用户名、至少 6 位密码和角色不能为空。"}), 400
    with connect() as conn:
        role = conn.execute("SELECT id FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not role:
            return jsonify({"error": "角色不存在。"}), 404
        try:
            conn.execute(
                """
                INSERT INTO users
                (id, username, password_hash, email, department, status, role_id, allowed_kb_ids, failed_attempts, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), username, hash_password(password), str(data.get("email", "")).strip(),
                 str(data.get("department", "")).strip(), str(data.get("status", "enabled")).strip() or "enabled",
                 role_id, json.dumps(parse_json_list(data.get("allowedKbIds", [])), ensure_ascii=False), 0, now_ms()),
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "用户名已存在。"}), 400
    return jsonify({"ok": True}), 201


@app.route("/api/users/<user_id>", methods=["PUT"])
def api_users_update(user_id):
    perm = _required_permission(request.path, "PUT")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    role_id = str(data.get("roleId", "")).strip()
    status = str(data.get("status", "enabled")).strip() or "enabled"
    if status not in {"enabled", "disabled"}:
        return jsonify({"error": "用户状态无效。"}), 400
    with connect() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "用户不存在。"}), 404
        role = conn.execute("SELECT id FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not role:
            return jsonify({"error": "角色不存在。"}), 404
        conn.execute(
            """
            UPDATE users SET email = ?, department = ?, status = ?, role_id = ?, allowed_kb_ids = ?, failed_attempts = ?
            WHERE id = ?
            """,
            (str(data.get("email", "")).strip(), str(data.get("department", "")).strip(), status, role_id,
             json.dumps(parse_json_list(data.get("allowedKbIds", [])), ensure_ascii=False),
             int(data.get("failedAttempts", 0) or 0), user_id),
        )
        password = str(data.get("password", ""))
        if password:
            if len(password) < 6:
                return jsonify({"error": "新密码至少 6 位。"}), 400
            conn.execute("UPDATE users SET password_hash = ?, failed_attempts = 0 WHERE id = ?", (hash_password(password), user_id))
    return jsonify({"ok": True})


@app.route("/api/users/<user_id>", methods=["DELETE"])
def api_users_delete(user_id):
    perm = _required_permission(request.path, "DELETE")
    current = _authorize(perm)
    if current and current.get("id") == user_id:
        return jsonify({"error": "不能删除当前登录账号。"}), 400
    with connect() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "用户不存在。"}), 404
        conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return jsonify({"ok": True})


@app.route("/api/roles", methods=["GET"])
def api_roles_list():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT r.*, COUNT(u.id) AS user_count
            FROM roles r LEFT JOIN users u ON u.role_id = r.id
            GROUP BY r.id ORDER BY r.builtin DESC, r.created_at ASC
            """
        ).fetchall()
    roles = []
    for row in rows:
        item = row_to_dict(row)
        item["permissions"] = normalize_permissions(item["permissions"])
        roles.append(item)
    return jsonify(roles)


@app.route("/api/roles", methods=["POST"])
def api_roles_create():
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "角色名称不能为空。"}), 400
    item = {
        "id": str(uuid.uuid4()), "name": name,
        "description": str(data.get("description", "")).strip(),
        "permissions": json.dumps(normalize_permissions(data.get("permissions", [])), ensure_ascii=False),
        "builtin": 0, "created_at": now_ms(),
    }
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO roles (id, name, description, permissions, builtin, created_at)
                VALUES (:id, :name, :description, :permissions, :builtin, :created_at)
                """, item,
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "角色名称已存在。"}), 400
    item["permissions"] = json.loads(item["permissions"])
    return jsonify(item), 201


@app.route("/api/roles/<role_id>", methods=["PUT"])
def api_roles_update(role_id):
    perm = _required_permission(request.path, "PUT")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "角色名称不能为空。"}), 400
    permissions = normalize_permissions(data.get("permissions", []))
    with connect() as conn:
        role = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not role:
            return jsonify({"error": "角色不存在。"}), 404
        conn.execute("UPDATE roles SET name = ?, description = ?, permissions = ? WHERE id = ?",
                     (name, str(data.get("description", "")).strip(), json.dumps(permissions, ensure_ascii=False), role_id))
    return jsonify({"ok": True})


@app.route("/api/roles/<role_id>", methods=["DELETE"])
def api_roles_delete(role_id):
    perm = _required_permission(request.path, "DELETE")
    _authorize(perm)
    with connect() as conn:
        role = conn.execute("SELECT builtin FROM roles WHERE id = ?", (role_id,)).fetchone()
        if not role:
            return jsonify({"error": "角色不存在。"}), 404
        if role["builtin"]:
            return jsonify({"error": "预设角色不能删除。"}), 400
        used = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role_id = ?", (role_id,)).fetchone()["n"]
        if used:
            return jsonify({"error": "该角色仍有关联用户，不能删除。"}), 400
        conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    return jsonify({"ok": True})


@app.route("/api/kbs", methods=["GET"])
def api_kbs_list():
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    keyword = (request.args.get("q") or "").strip()
    department = (request.args.get("department") or "").strip()
    sort = request.args.get("sort", "created_at")
    direction = "ASC" if request.args.get("dir", "desc").lower() == "asc" else "DESC"
    sort_column = {"name": "k.name", "department": "k.department", "created_at": "k.created_at"}.get(sort, "k.created_at")
    clauses = ["k.deleted = 0"]
    args: list = []
    if keyword:
        clauses.append("(k.name LIKE ? OR k.description LIKE ? OR k.owner LIKE ?)")
        args.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if department:
        clauses.append("k.department LIKE ?")
        args.append(f"%{department}%")
    scope_clause, scope_args = restricted_kb_clause(user, "k.id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT k.*, COUNT(DISTINCT d.id) AS document_count, COUNT(c.id) AS chunk_count
            FROM knowledge_bases k
            LEFT JOIN documents d ON d.kb_id = k.id
            LEFT JOIN chunks c ON c.kb_id = k.id
            WHERE {" AND ".join(clauses)}
            GROUP BY k.id ORDER BY {sort_column} {direction}
            """, tuple(args),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/api/kbs", methods=["POST"])
def api_kbs_create():
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "知识库名称不能为空。"}), 400
    with connect() as conn:
        default_model = get_default_model_name(conn)
    item = {
        "id": str(uuid.uuid4()), "name": name,
        "description": str(data.get("description", "")).strip(),
        "category": str(data.get("category", DEFAULT_CATEGORIES[0])).strip(),
        "department": str(data.get("department", "")).strip(),
        "owner": str(data.get("owner", "")).strip(),
        "embedding_model": str(data.get("embeddingModel", default_model)).strip(),
        "status": "active", "created_at": now_ms(),
    }
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_bases
            (id, name, description, category, department, owner, embedding_model, status, created_at)
            VALUES (:id, :name, :description, :category, :department, :owner, :embedding_model, :status, :created_at)
            """, item,
        )
        allowed = user.get("allowedKbIds") if user else []
        if allowed and "*" not in user.get("permissions", []):
            allowed = sorted(set(allowed + [item["id"]]))
            conn.execute("UPDATE users SET allowed_kb_ids = ? WHERE id = ?", (json.dumps(allowed), user["id"]))
    return jsonify(item), 201


@app.route("/api/kbs/<kb_id>", methods=["PUT"])
def api_kbs_update(kb_id):
    perm = _required_permission(request.path, "PUT")
    user = _authorize(perm)
    if not can_access_kb(user, kb_id):
        return jsonify({"error": "当前账号无权操作该知识库。"}), 403
    data = request.get_json(silent=True) or {}
    with connect() as conn:
        existing = conn.execute("SELECT id FROM knowledge_bases WHERE id = ? AND deleted = 0", (kb_id,)).fetchone()
        if not existing:
            return jsonify({"error": "知识库不存在。"}), 404
        default_model = get_default_model_name(conn)
        conn.execute(
            """
            UPDATE knowledge_bases SET name = ?, description = ?, category = ?, department = ?, owner = ?, embedding_model = ?
            WHERE id = ?
            """,
            (str(data.get("name", "")).strip(), str(data.get("description", "")).strip(),
             str(data.get("category", DEFAULT_CATEGORIES[0])).strip(), str(data.get("department", "")).strip(),
             str(data.get("owner", "")).strip(), str(data.get("embeddingModel", default_model)).strip(), kb_id),
        )
    return jsonify({"ok": True})


@app.route("/api/kbs/<kb_id>", methods=["DELETE"])
def api_kbs_delete(kb_id):
    perm = _required_permission(request.path, "DELETE")
    user = _authorize(perm)
    if not can_access_kb(user, kb_id):
        return jsonify({"error": "当前账号无权操作该知识库。"}), 403
    mode = request.args.get("mode", "logical")
    with connect() as conn:
        if mode == "physical":
            docs = conn.execute("SELECT id, path FROM documents WHERE kb_id = ?", (kb_id,)).fetchall()
            for doc in docs:
                conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc["id"],))
                conn.execute("DELETE FROM documents WHERE id = ?", (doc["id"],))
                path = Path(doc["path"])
                if path.exists() and UPLOAD_DIR in path.resolve().parents:
                    path.unlink()
            conn.execute("DELETE FROM chunks WHERE kb_id = ?", (kb_id,))
            conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        else:
            conn.execute("UPDATE knowledge_bases SET deleted = 1, status = 'deleted' WHERE id = ?", (kb_id,))
    return jsonify({"ok": True})


@app.route("/api/kbs/<kb_id>/clone", methods=["POST"])
def api_kbs_clone(kb_id):
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    if not can_access_kb(user, kb_id):
        return jsonify({"error": "当前账号无权操作该知识库。"}), 403
    data = request.get_json(silent=True) or {}
    with connect() as conn:
        source = conn.execute("SELECT * FROM knowledge_bases WHERE id = ? AND deleted = 0", (kb_id,)).fetchone()
        if not source:
            return jsonify({"error": "知识库不存在。"}), 404
        new_kb_id = str(uuid.uuid4())
        new_name = str(data.get("name") or f"{source['name']} 副本").strip()
        conn.execute(
            """
            INSERT INTO knowledge_bases
            (id, name, description, category, department, owner, embedding_model, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_kb_id, new_name, source["description"], source["category"], source["department"],
             source["owner"], source["embedding_model"], "active", now_ms()),
        )
        docs = conn.execute("SELECT * FROM documents WHERE kb_id = ?", (kb_id,)).fetchall()
        for doc in docs:
            old_path = Path(doc["path"])
            new_doc_id = str(uuid.uuid4())
            new_path = UPLOAD_DIR / f"{new_doc_id}.{doc['file_type']}"
            if old_path.exists():
                new_path.write_bytes(old_path.read_bytes())
            conn.execute(
                """
                INSERT INTO documents (id, kb_id, name, file_type, size, path, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_doc_id, new_kb_id, doc["name"], doc["file_type"], doc["size"], str(new_path), doc["status"], now_ms()),
            )
            chunks = conn.execute("SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc["id"],)).fetchall()
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (id, kb_id, doc_id, chunk_index, text, tokens, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), new_kb_id, new_doc_id, chunk["chunk_index"], chunk["text"], chunk["tokens"], now_ms()),
                )
    return jsonify({"ok": True, "id": new_kb_id, "name": new_name}), 201


@app.route("/api/documents", methods=["GET"])
def api_documents_list():
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    kb_id = request.args.get("kbId")
    keyword = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "created_at")
    direction = "ASC" if request.args.get("dir", "desc").lower() == "asc" else "DESC"
    sort_column = "d.name" if sort == "name" else "d.created_at"
    clauses = ["k.deleted = 0"]
    args: list = []
    if kb_id:
        if not can_access_kb(user, kb_id):
            return jsonify({"error": "当前账号无权访问该知识库。"}), 403
        clauses.append("d.kb_id = ?")
        args.append(kb_id)
    if keyword:
        clauses.append("d.name LIKE ?")
        args.append(f"%{keyword}%")
    scope_clause, scope_args = restricted_kb_clause(user, "d.kb_id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT d.*, k.name AS kb_name, COUNT(c.id) AS chunk_count
            FROM documents d JOIN knowledge_bases k ON k.id = d.kb_id
            LEFT JOIN chunks c ON c.doc_id = d.id
            WHERE {" AND ".join(clauses)}
            GROUP BY d.id ORDER BY {sort_column} {direction}
            """, tuple(args),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/api/documents/<doc_id>/preview", methods=["GET"])
def api_document_preview(doc_id):
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    keyword = (request.args.get("q") or "").strip()
    with connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return jsonify({"error": "文档不存在。"}), 404
        if not can_access_kb(user, doc["kb_id"]):
            return jsonify({"error": "当前账号无权访问该文档。"}), 403
        chunks = conn.execute("SELECT id, chunk_index, text FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)).fetchall()
    path = Path(doc["path"])
    original = ""
    if path.exists():
        try:
            original = extract_text(path, doc["file_type"])
        except Exception:
            original = path.read_text(encoding="utf-8", errors="ignore")
    chunk_items = [row_to_dict(row) for row in chunks]
    if keyword:
        chunk_items = [item for item in chunk_items if keyword in item["text"]]
    return jsonify({"document": row_to_dict(doc), "original": original, "chunks": chunk_items})


@app.route("/api/documents/<doc_id>", methods=["PUT"])
def api_document_update(doc_id):
    perm = _required_permission(request.path, "PUT")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    config = ensure_config_file()
    text = clean_text(str(data.get("text", "")))
    chunk_size = max(80, min(2000, int(data.get("chunkSize") or config["chunkSize"])))
    chunk_overlap = max(0, min(chunk_size - 1, int(data.get("chunkOverlap") or config["chunkOverlap"])))
    if not text:
        return jsonify({"error": "文档内容不能为空。"}), 400
    with connect() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return jsonify({"error": "文档不存在。"}), 404
        if not can_access_kb(user, doc["kb_id"]):
            return jsonify({"error": "当前账号无权操作该文档。"}), 403
        path = Path(doc["path"])
        path.write_text(text, encoding="utf-8")
        conn.execute("UPDATE documents SET size = ?, status = ? WHERE id = ?", (len(text.encode("utf-8")), "ready", doc_id))
        insert_chunks(conn, doc["kb_id"], doc_id, text, chunk_size, chunk_overlap, config)
        chunk_count = conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()["n"]
    return jsonify({"ok": True, "chunkCount": chunk_count})


@app.route("/api/documents/<doc_id>", methods=["DELETE"])
def api_document_delete(doc_id):
    perm = _required_permission(request.path, "DELETE")
    user = _authorize(perm)
    with connect() as conn:
        row = conn.execute("SELECT path, kb_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row and not can_access_kb(user, row["kb_id"]):
            return jsonify({"error": "当前账号无权删除该文档。"}), 403
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    if row:
        path = Path(row["path"])
        if path.exists() and UPLOAD_DIR in path.resolve().parents:
            path.unlink()
    return jsonify({"ok": True})


@app.route("/api/documents/batch-delete", methods=["POST"])
def api_documents_batch_delete():
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    ids = [str(item) for item in data.get("ids", []) if item]
    deleted = 0
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, path, kb_id FROM documents WHERE id IN ({','.join('?' for _ in ids)})", tuple(ids),
        ).fetchall() if ids else []
        for row in rows:
            if not can_access_kb(user, row["kb_id"]):
                continue
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (row["id"],))
            conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
            path = Path(row["path"])
            if path.exists() and UPLOAD_DIR in path.resolve().parents:
                path.unlink()
            deleted += 1
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/kbs/<kb_id>/documents", methods=["POST"])
def api_kbs_upload(kb_id):
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    if not can_access_kb(user, kb_id):
        return jsonify({"error": "当前账号无权上传到该知识库。"}), 403
    config = ensure_config_file()
    if "file" not in request.files:
        return jsonify({"error": "请选择文件。"}), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "请选择文件。"}), 400
    filename = os.path.basename(upload.filename)
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_type not in {"txt", "md", "docx", "pdf"}:
        return jsonify({"error": "仅支持 txt、md、docx、pdf 文件。"}), 400
    doc_id = str(uuid.uuid4())
    target = UPLOAD_DIR / f"{doc_id}.{file_type}"
    data = upload.read()
    max_bytes = int(config["maxUploadMb"]) * 1024 * 1024
    if len(data) > max_bytes:
        return jsonify({"error": f"文件超过 {config['maxUploadMb']} MB 上传限制。"}), 400
    chunk_size = max(80, min(2000, int(request.form.get("chunkSize") or config["chunkSize"])))
    chunk_overlap = max(0, min(chunk_size - 1, int(request.form.get("chunkOverlap") or config["chunkOverlap"])))
    target.write_bytes(data)
    try:
        text = extract_text(target, file_type)
        if not text:
            raise ValueError("未解析到有效文本。")
        status = "ready"
    except Exception as exc:
        text = ""
        status = f"failed: {exc}"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, kb_id, name, file_type, size, path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, kb_id, filename, file_type, len(data), str(target), status, now_ms()),
        )
        if text:
            insert_chunks(conn, kb_id, doc_id, text, chunk_size, chunk_overlap, config)
    return jsonify({"id": doc_id, "name": filename, "status": status, "chunkSize": chunk_size, "chunkOverlap": chunk_overlap}), 201


@app.route("/api/split-preview", methods=["POST"])
def api_split_preview():
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    config = ensure_config_file()
    text = clean_text(str(data.get("text", "")))
    chunk_size = max(80, min(2000, int(data.get("chunkSize") or config["chunkSize"])))
    chunk_overlap = max(0, min(chunk_size - 1, int(data.get("chunkOverlap") or config["chunkOverlap"])))
    chunks = split_text(text, chunk_size, chunk_overlap) if text else []
    return jsonify({"chunkSize": chunk_size, "chunkOverlap": chunk_overlap, "chunks": chunks})


@app.route("/api/vectors/preview", methods=["GET"])
def api_vectors_preview():
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    kb_id = request.args.get("kbId")
    keyword = (request.args.get("q") or "").strip()
    limit = max(1, min(50, int(request.args.get("limit", "12"))))
    clauses = ["k.deleted = 0"]
    args: list = []
    if kb_id:
        if not can_access_kb(user, kb_id):
            return jsonify({"error": "当前账号无权访问该知识库。"}), 403
        clauses.append("c.kb_id = ?")
        args.append(kb_id)
    if keyword:
        clauses.append("c.text LIKE ?")
        args.append(f"%{keyword}%")
    scope_clause, scope_args = restricted_kb_clause(user, "c.kb_id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.chunk_index, c.text, c.tokens, d.name AS document_name,
                   k.name AS kb_name, k.embedding_model,
                   vm.dimension AS normalized_dimension, vm.norm AS normalized_norm, vm.normalized_terms
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            JOIN knowledge_bases k ON k.id = c.kb_id
            LEFT JOIN vector_metadata vm ON vm.chunk_id = c.id
            WHERE {" AND ".join(clauses)}
            ORDER BY c.created_at DESC LIMIT ?
            """, tuple(args + [limit]),
        ).fetchall()
    query_tokens = tokenize(keyword)
    items = []
    for row in rows:
        tokens = json.loads(row["tokens"])
        vector_terms = Counter(tokens)
        normalized_terms = json.loads(row["normalized_terms"]) if row["normalized_terms"] else []
        preview_terms = [
            term["term"] if isinstance(term, dict) else str(term) for term in normalized_terms[:10]
        ] or [token for token, _ in vector_terms.most_common(10)]
        similarity = score(query_tokens, tokens) if keyword else 0.0
        items.append({
            "id": row["id"], "chunkIndex": row["chunk_index"], "document": row["document_name"],
            "knowledgeBase": row["kb_name"], "model": row["embedding_model"],
            "dimension": row["normalized_dimension"] or len(vector_terms),
            "norm": row["normalized_norm"] or 0, "similarity": similarity,
            "terms": preview_terms, "text": row["text"][:260],
        })
    return jsonify({"items": items, "query": keyword})


@app.route("/api/vectors/rebuild", methods=["POST"])
def api_vectors_rebuild():
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    kb_id = data.get("kbId") or None
    doc_ids = [str(item) for item in data.get("docIds", []) if item]
    config = ensure_config_file()
    chunk_size = max(80, min(2000, int(data.get("chunkSize") or config["chunkSize"])))
    chunk_overlap = max(0, min(chunk_size - 1, int(data.get("chunkOverlap") or config["chunkOverlap"])))
    clauses = ["k.deleted = 0"]
    args: list = []
    if kb_id:
        if not can_access_kb(user, kb_id):
            return jsonify({"error": "当前账号无权操作该知识库。"}), 403
        clauses.append("d.kb_id = ?")
        args.append(kb_id)
    if doc_ids:
        clauses.append(f"d.id IN ({','.join('?' for _ in doc_ids)})")
        args.extend(doc_ids)
    scope_clause, scope_args = restricted_kb_clause(user, "d.kb_id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        docs = conn.execute(
            f"""
            SELECT d.* FROM documents d JOIN knowledge_bases k ON k.id = d.kb_id
            WHERE {" AND ".join(clauses)} ORDER BY d.created_at ASC
            """, tuple(args),
        ).fetchall()
        progress = []
        total_chunks = 0
        total = len(docs)
        for index, doc in enumerate(docs, start=1):
            chunk_count = rebuild_document_vectors(conn, doc, chunk_size, chunk_overlap, config)
            total_chunks += chunk_count
            progress.append({
                "documentId": doc["id"], "document": doc["name"],
                "chunks": chunk_count, "percent": round(index / total * 100) if total else 100,
            })
    return jsonify({
        "ok": True, "documents": len(progress), "chunks": total_chunks,
        "chunkSize": chunk_size, "chunkOverlap": chunk_overlap, "progress": progress,
    })


@app.route("/api/vectors/normalize", methods=["POST"])
def api_vectors_normalize():
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    kb_id = data.get("kbId") or None
    clauses = ["k.deleted = 0"]
    args: list = []
    if kb_id:
        if not can_access_kb(user, kb_id):
            return jsonify({"error": "当前账号无权操作该知识库。"}), 403
        clauses.append("c.kb_id = ?")
        args.append(kb_id)
    scope_clause, scope_args = restricted_kb_clause(user, "c.kb_id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.tokens, d.name AS document_name
            FROM chunks c JOIN documents d ON d.id = c.doc_id JOIN knowledge_bases k ON k.id = c.kb_id
            WHERE {" AND ".join(clauses)} ORDER BY c.doc_id, c.chunk_index
            """, tuple(args),
        ).fetchall()
        progress = []
        total_norm = 0.0
        total = len(rows)
        for index, row in enumerate(rows, start=1):
            dimension, norm, terms = normalize_tokens(json.loads(row["tokens"]))
            total_norm += norm
            conn.execute(
                """
                INSERT INTO vector_metadata (chunk_id, dimension, norm, normalized_terms, normalized_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    dimension = excluded.dimension, norm = excluded.norm,
                    normalized_terms = excluded.normalized_terms, normalized_at = excluded.normalized_at
                """,
                (row["id"], dimension, norm, json.dumps(terms, ensure_ascii=False), now_ms()),
            )
            if index == total or index % 10 == 0:
                progress.append({"document": row["document_name"], "percent": round(index / total * 100) if total else 100})
    average_norm = round(total_norm / total, 4) if total else 0
    return jsonify({"ok": True, "chunks": total, "averageNorm": average_norm, "progress": progress})


@app.route("/api/vectors/deduplicate", methods=["POST"])
def api_vectors_deduplicate():
    perm = _required_permission(request.path, "POST")
    user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    kb_id = data.get("kbId") or None
    threshold = max(0.5, min(1.0, float(data.get("threshold") or 0.92)))
    clauses = ["k.deleted = 0"]
    args: list = []
    if kb_id:
        if not can_access_kb(user, kb_id):
            return jsonify({"error": "当前账号无权操作该知识库。"}), 403
        clauses.append("c.kb_id = ?")
        args.append(kb_id)
    scope_clause, scope_args = restricted_kb_clause(user, "c.kb_id")
    if scope_clause:
        clauses.append(scope_clause)
        args.extend(scope_args)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.text, c.tokens, c.doc_id, d.name AS document_name
            FROM chunks c JOIN documents d ON d.id = c.doc_id JOIN knowledge_bases k ON k.id = c.kb_id
            WHERE {" AND ".join(clauses)} ORDER BY c.doc_id, c.chunk_index
            """, tuple(args),
        ).fetchall()
        kept: list[tuple[str, list[str], str]] = []
        duplicates = []
        for row in rows:
            text_key = clean_text(row["text"])
            tokens = json.loads(row["tokens"])
            duplicate_of = ""
            duplicate_score = 0.0
            for kept_text, kept_tokens, kept_id in kept:
                if text_key == kept_text:
                    duplicate_of = kept_id
                    duplicate_score = 1.0
                    break
                similarity = token_similarity(tokens, kept_tokens)
                if similarity >= threshold:
                    duplicate_of = kept_id
                    duplicate_score = similarity
                    break
            if duplicate_of:
                duplicates.append({
                    "id": row["id"], "document": row["document_name"],
                    "duplicateOf": duplicate_of, "similarity": duplicate_score,
                })
                conn.execute("DELETE FROM vector_metadata WHERE chunk_id = ?", (row["id"],))
                conn.execute("DELETE FROM chunks WHERE id = ?", (row["id"],))
            else:
                kept.append((text_key, tokens, row["id"]))
    return jsonify({"ok": True, "removed": len(duplicates), "duplicates": duplicates[:30], "threshold": threshold})


@app.route("/api/system/config", methods=["GET"])
def api_system_config_get():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    return jsonify(ensure_config_file())


@app.route("/api/system/config", methods=["POST"])
def api_system_config_save():
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    config = save_system_config(data)
    return jsonify(config)


@app.route("/api/ollama/models", methods=["GET"])
def api_ollama_models():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    config = ensure_config_file()
    base_url = str(request.args.get("url") or config.get("ollamaUrl") or "http://127.0.0.1:11434").strip().rstrip("/")
    timeout = max(1, min(15, int(config.get("retrievalTimeoutSeconds") or 10)))
    try:
        data = ollama_json_request(base_url, "/api/tags", None, timeout)
        models = []
        for item in data.get("models") or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            models.append({"name": name, "size": int(item.get("size") or 0), "modifiedAt": item.get("modified_at") or ""})
        models.sort(key=lambda item: item["name"].lower())
        return jsonify({"ok": True, "url": base_url, "models": models})
    except Exception as exc:
        return jsonify({"ok": False, "url": base_url, "models": [], "error": f"无法连接 Ollama：{exc}"}), 502


@app.route("/api/models", methods=["GET"])
def api_models_list():
    perm = _required_permission(request.path, "GET")
    _authorize(perm)
    with connect() as conn:
        seed_embedding_models(conn)
        known_paths = {row["path"] for row in conn.execute("SELECT path FROM embedding_models").fetchall()}
        for model in discover_local_models():
            if model["path"] in known_paths:
                continue
            conn.execute(
                """
                INSERT INTO embedding_models (id, name, path, dimension, description, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), model["name"], model["path"], model["dimension"],
                 model["description"], model["is_default"], now_ms()),
            )
        rows = conn.execute("SELECT * FROM embedding_models ORDER BY is_default DESC, created_at ASC").fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.route("/api/models", methods=["POST"])
def api_models_create():
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "模型名称不能为空。"}), 400
    item = {
        "id": str(uuid.uuid4()), "name": name,
        "path": str(data.get("path", "")).strip(),
        "dimension": max(0, int(data.get("dimension") or 0)),
        "description": str(data.get("description", "")).strip(),
        "is_default": 1 if data.get("isDefault") else 0, "created_at": now_ms(),
    }
    with connect() as conn:
        if item["is_default"]:
            conn.execute("UPDATE embedding_models SET is_default = 0")
        try:
            conn.execute(
                """
                INSERT INTO embedding_models (id, name, path, dimension, description, is_default, created_at)
                VALUES (:id, :name, :path, :dimension, :description, :is_default, :created_at)
                """, item,
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "模型名称已存在。"}), 400
    return jsonify(item), 201


@app.route("/api/models/<model_id>/default", methods=["POST"])
def api_models_set_default(model_id):
    perm = _required_permission(request.path, "POST")
    _authorize(perm)
    with connect() as conn:
        model = conn.execute("SELECT id FROM embedding_models WHERE id = ?", (model_id,)).fetchone()
        if not model:
            return jsonify({"error": "模型不存在。"}), 404
        conn.execute("UPDATE embedding_models SET is_default = 0")
        conn.execute("UPDATE embedding_models SET is_default = 1 WHERE id = ?", (model_id,))
    return jsonify({"ok": True})


@app.route("/api/kb-test", methods=["POST"])
def api_kb_test():
    perm = _required_permission(request.path, "POST")
    current_user = _authorize(perm)
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "测试问题不能为空。"}), 400
    kb_id = data.get("kbId") or None
    if kb_id and not can_access_kb(current_user, kb_id):
        return jsonify({"error": "当前账号无权访问该知识库。"}), 403
    config = ensure_config_file()
    top_k = max(1, min(20, int(data.get("topK") or config.get("defaultTopK") or DEFAULT_TOP_K)))
    threshold = max(0.0, min(1.0, float(data.get("threshold") or config.get("defaultThreshold") or DEFAULT_THRESHOLD)))
    reliable_threshold = max(threshold, float(config.get("minReliableScore") or MIN_RELIABLE_SCORE))
    context_turns = max(0, min(50, int(config.get("contextTurns") or DEFAULT_CONTEXT_TURNS)))
    answer_mode = str(data.get("answerMode") or config.get("answerMode") or "enhanced").strip()
    if answer_mode not in {"strict", "enhanced", "free"}:
        answer_mode = "enhanced"
    client_context = normalize_client_context(data.get("contextMessages"), context_turns * 2)
    safe_question = apply_sensitive_filter(question, config)
    skip_reason = should_skip_kb_retrieval(safe_question)
    if skip_reason:
        debug = build_retrieval_debug(
            question,
            safe_question,
            "",
            kb_id,
            [],
            threshold,
            reliable_threshold,
            answer_mode,
            False,
            "skip",
        )
        debug["status"] = skip_reason
        return jsonify({
            "question": question,
            "effectiveQuestion": safe_question,
            "searchQuery": "",
            "answerMode": answer_mode,
            "threshold": threshold,
            "reliableThreshold": reliable_threshold,
            "matched": False,
            "skipped": True,
            "skipReason": skip_reason,
            "debug": debug,
            "hits": [],
        })
    effective_question = rewrite_contextual_question(safe_question, client_context, [])
    search_query = effective_question
    with connect() as conn:
        hits = search_chunks_for_user(conn, search_query, kb_id, top_k, current_user, config)
    focused_hits = focus_hits_for_question(effective_question, hits)
    debug = build_retrieval_debug(
        question,
        effective_question,
        search_query,
        kb_id,
        focused_hits,
        threshold,
        reliable_threshold,
        answer_mode,
        False,
        "test",
    )
    return jsonify({
        "question": question,
        "effectiveQuestion": effective_question,
        "searchQuery": search_query,
        "answerMode": answer_mode,
        "threshold": threshold,
        "reliableThreshold": reliable_threshold,
        "matched": bool(focused_hits and focused_hits[0]["score"] >= reliable_threshold),
        "debug": debug,
        "hits": debug["hits"],
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    perm = _required_permission(request.path, "POST")
    current_user = _authorize(perm)
    started = now_ms()
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "问题不能为空。"}), 400
    user_id = current_user["id"] if current_user else ""
    kb_id = data.get("kbId") or None
    if kb_id and not can_access_kb(current_user, kb_id):
        return jsonify({"error": "当前账号无权访问该知识库。"}), 403
    config = ensure_config_file()
    answer_mode = str(data.get("answerMode") or config.get("answerMode") or "enhanced").strip()
    if answer_mode not in {"strict", "enhanced", "free"}:
        answer_mode = "enhanced"
    conversation_id = data.get("conversationId") or str(uuid.uuid4())
    top_k = max(1, min(20, int(data.get("topK") or config.get("defaultTopK") or DEFAULT_TOP_K)))
    threshold = max(0.0, min(1.0, float(data.get("threshold") or config.get("defaultThreshold") or DEFAULT_THRESHOLD)))
    reliable_threshold = max(threshold, float(config.get("minReliableScore") or MIN_RELIABLE_SCORE))
    context_turns = max(0, min(50, int(config.get("contextTurns") or DEFAULT_CONTEXT_TURNS)))
    context_max_chars = max(0, min(20000, int(config.get("contextMaxChars") or 2000)))
    max_answer_chars = max(100, min(5000, int(config.get("maxAnswerChars") or 1200)))
    fallback_answer = str(config.get("fallbackAnswer") or DEFAULT_SYSTEM_CONFIG["fallbackAnswer"]).strip()
    safe_question = apply_sensitive_filter(question, config)
    request_timeout_ms = max(5, min(300, int(config.get("requestTimeoutSeconds") or 30))) * 1000
    retrieval_timeout_ms = max(1, min(120, int(config.get("retrievalTimeoutSeconds") or 10))) * 1000
    answer_timeout_ms = max(1, min(120, int(config.get("answerTimeoutSeconds") or 10))) * 1000
    client_context = normalize_client_context(data.get("contextMessages"), context_turns * 2)
    with connect() as conn:
        existing = conn.execute("SELECT id, user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if existing and existing["user_id"] and existing["user_id"] != user_id:
            conversation_id = str(uuid.uuid4())
            existing = None
        if not existing:
            conn.execute("INSERT INTO conversations (id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                         (conversation_id, user_id, now_ms(), now_ms()))
        elif not existing["user_id"]:
            conn.execute("UPDATE conversations SET user_id = ? WHERE id = ?", (user_id, conversation_id))
        history = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, context_turns * 2),
        ).fetchall()
        direct_answer = (
            match_refusal_answer(question, config)
            or resolve_history_meta_answer(safe_question, client_context, history)
            or match_dialog_rule_answer(question, config)
            or answer_greeting(safe_question)
        )
        if direct_answer:
            answer = apply_sensitive_filter(format_answer_for_question(question, direct_answer), config)
            sources, best_score, llm_enhanced = [], 0.0, False
            debug = build_retrieval_debug(
                safe_question,
                safe_question,
                "",
                kb_id,
                [],
                threshold,
                reliable_threshold,
                answer_mode,
                False,
                "direct",
            )
            created = now_ms()
            conn.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                         (str(uuid.uuid4()), conversation_id, "user", safe_question, created))
            conn.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                         (str(uuid.uuid4()), conversation_id, "assistant", answer, created + 1))
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (created, conversation_id))
            conn.execute(
                """
                INSERT INTO chat_logs (id, conversation_id, user_id, question, answer, kb_id, sources, score, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), conversation_id, user_id, safe_question, answer, kb_id, "[]", best_score, now_ms() - started, created),
            )
            return jsonify({
                "conversationId": conversation_id, "question": safe_question, "answer": answer,
                "sources": sources, "score": best_score, "llmEnhanced": llm_enhanced,
                "answerMode": answer_mode, "debug": debug, "latencyMs": now_ms() - started,
            })
        effective_question = rewrite_contextual_question(safe_question, client_context, history)
        memory_context = build_compact_memory(
            safe_question,
            client_context,
            history,
            max_chars=min(1200, max(300, context_max_chars)),
            max_messages=min(12, max(4, context_turns * 2)),
        )
        context = ""
        if context_turns and should_use_history(question):
            if client_context:
                context_items = client_context[-context_turns * 2:]
                context = " ".join(f"{item['role']}：{item['content']}" for item in context_items)
            else:
                recent_user_questions = [row["content"] for row in reversed(history) if row["role"] == "user"][-2:]
                context = " ".join(recent_user_questions)
            if context_max_chars and len(context) > context_max_chars:
                context = context[-context_max_chars:]
        search_query = effective_question if effective_question != safe_question else f"{context} {safe_question}".strip()
        hits = search_chunks_for_user(conn, search_query, kb_id, top_k, current_user, config)
        if now_ms() - started > retrieval_timeout_ms:
            return jsonify({"error": "检索用时较长，请稍后重试或缩小检索范围。"}), 504
        answer, sources, best_score = build_answer(effective_question, hits, reliable_threshold, max_answer_chars, fallback_answer)
        llm_enhanced = False
        answer_source = "knowledge" if sources and best_score >= reliable_threshold else "fallback"
        if answer_mode in {"enhanced", "free"} and sources and best_score >= reliable_threshold:
            llm_hits = focus_hits_for_question(effective_question, hits)
            llm_hits = [hit for hit in llm_hits if hit["score"] >= reliable_threshold]
            answer_body = answer.split("\n\n来源：", 1)[0]
            answer_body = remove_wrong_hero_heading(effective_question, answer_body)
            answer_body, llm_enhanced = enhance_answer_with_llm(
                effective_question,
                llm_hits,
                answer_body,
                config,
                max_answer_chars,
                memory_context,
            )
            suffix = "（LLM 增强）" if llm_enhanced else ""
            answer = f"{answer_body}\n\n来源：{sources[0]['document']}；相似度 {best_score:.2f}{suffix}"
        elif answer_mode == "free" and not sources:
            free_answer, llm_enhanced = generate_free_answer_with_llm(
                effective_question,
                fallback_answer,
                config,
                max_answer_chars,
                memory_context,
            )
            if llm_enhanced:
                answer = free_answer
                answer_source = "free"
            else:
                answer_source = "fallback"
        debug = build_retrieval_debug(
            safe_question,
            effective_question,
            search_query,
            kb_id,
            focus_hits_for_question(effective_question, hits),
            threshold,
            reliable_threshold,
            answer_mode,
            llm_enhanced,
            answer_source,
        )
        answer = apply_sensitive_filter(format_answer_for_question(question, answer), config)
        if now_ms() - started > answer_timeout_ms or now_ms() - started > request_timeout_ms:
            return jsonify({"error": "回答生成用时较长，请稍后重试或缩短问题。"}), 504
        created = now_ms()
        conn.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), conversation_id, "user", safe_question, created))
        conn.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), conversation_id, "assistant", answer, created + 1))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (created, conversation_id))
        conn.execute(
            """
            INSERT INTO chat_logs (id, conversation_id, user_id, question, answer, kb_id, sources, score, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), conversation_id, user_id, safe_question, answer, kb_id,
             json.dumps(sources, ensure_ascii=False), best_score, now_ms() - started, created),
        )
    return jsonify({
        "conversationId": conversation_id, "question": safe_question, "answer": answer,
        "sources": sources, "score": best_score, "llmEnhanced": llm_enhanced,
        "answerMode": answer_mode, "debug": debug, "latencyMs": now_ms() - started,
    })


@app.route("/api/logs", methods=["GET"])
def api_logs():
    perm = _required_permission(request.path, "GET")
    user = _authorize(perm)
    scope_clause, scope_args = restricted_kb_clause(user, "l.kb_id")
    where = f"WHERE ({scope_clause} OR l.kb_id IS NULL)" if scope_clause else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT l.*, k.name AS kb_name, u.username AS username,
                   COALESCE(NULLIF(u.display_name, ''), u.username, '未归属账号') AS display_name
            FROM chat_logs l
            LEFT JOIN knowledge_bases k ON k.id = l.kb_id
            LEFT JOIN users u ON u.id = l.user_id
            {where} ORDER BY l.created_at DESC LIMIT 80
            """, tuple(scope_args),
        ).fetchall()
    logs = []
    for row in rows:
        item = row_to_dict(row)
        item["sources"] = json.loads(item["sources"])
        logs.append(item)
    return jsonify(logs)


# ── 启动入口 ──────────────────────────────────────────────────────
def main() -> None:
    init_db()
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    print(f"王者荣耀智能客服机器人已启动：http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
