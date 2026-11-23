import asyncio
import hashlib
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import parse_qsl

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
DB_PATH = os.getenv("DATABASE_PATH", "taskflow.sqlite3")

bot = Bot(BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()
polling_task = None


@dp.message(CommandStart())
async def start_command(message: Message):
    if not WEBAPP_URL.startswith("https://"):
        await message.answer(
            "TaskFlow запущен, но HTTPS-адрес приложения пока не настроен. "
            "Добавь WEBAPP_URL в переменные окружения Render."
        )
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="Открыть TaskFlow",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]],
        resize_keyboard=True
    )
    await message.answer(
        "Добро пожаловать в TaskFlow. Планируй задачи и отслеживай прогресс.",
        reply_markup=keyboard
    )


async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Личное',
                priority TEXT NOT NULL DEFAULT 'Обычный',
                done INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        await conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    await init_db()
    if bot:
        polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False)
        )
    yield
    if polling_task and not polling_task.done():
        await dp.stop_polling()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    if bot:
        await bot.session.close()


app = FastAPI(title="TaskFlow Mini App", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def validate_init_data(init_data: str) -> int:
    if not BOT_TOKEN:
        raise HTTPException(503, "Bot token is not configured")
    if not init_data:
        raise HTTPException(401, "Open this app from Telegram")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Invalid Telegram authorization data")

    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(401, "Invalid Telegram authorization date")

    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > 86400:
        raise HTTPException(401, "Telegram authorization data expired")

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Telegram authorization check failed")

    try:
        user = json.loads(data.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Telegram user is missing")
    return user_id


def current_user(authorization: str | None) -> int:
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(401, "Missing Telegram init data")
    return validate_init_data(authorization[4:])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: Literal["Личное", "Учёба", "Работа", "Другое"] = "Личное"
    priority: Literal["Обычный", "Высокий", "Низкий"] = "Обычный"

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be empty")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: Literal["Личное", "Учёба", "Работа", "Другое"] | None = None
    priority: Literal["Обычный", "Высокий", "Низкий"] | None = None
    done: bool | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Task title cannot be null")
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be empty")
        return value

    @field_validator("category", "priority")
    @classmethod
    def reject_null_values(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/tasks")
async def list_tasks(authorization: str | None = Header(default=None)):
    uid = current_user(authorization)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tasks WHERE user_id=? ORDER BY done ASC, id DESC",
            (uid,)
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@app.post("/api/tasks")
async def create_task(
    task: TaskCreate,
    authorization: str | None = Header(default=None)
):
    uid = current_user(authorization)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "INSERT INTO tasks(user_id,title,category,priority,created_at) "
            "VALUES(?,?,?,?,?)",
            (uid, task.title, task.category, task.priority, int(time.time()))
        )
        task_id = cursor.lastrowid
        await conn.commit()
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        )
        row = await cursor.fetchone()
    return dict(row)


@app.patch("/api/tasks/{task_id}")
async def update_task(
    task_id: int,
    task: TaskUpdate,
    authorization: str | None = Header(default=None)
):
    uid = current_user(authorization)
    updates = task.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No changes supplied")
    if "done" in updates:
        updates["done"] = int(updates["done"])

    # Column names originate only from the explicitly declared Pydantic model.
    sql = ", ".join(f"{key}=?" for key in updates)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            f"UPDATE tasks SET {sql} WHERE id=? AND user_id=?",
            (*updates.values(), task_id, uid)
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Task not found")
        await conn.commit()
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        )
        row = await cursor.fetchone()
    return dict(row)


@app.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: int,
    authorization: str | None = Header(default=None)
):
    uid = current_user(authorization)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "DELETE FROM tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        )
        await conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(404, "Task not found")
    return {"ok": True}
