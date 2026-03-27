"""
Telegram бот Джонни — вежливый, грамотный, но живой
"""

import asyncio
import json
import time
import random
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from playwright.async_api import async_playwright

# ========== КОНФИГ ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_CHAT_URL = os.getenv("DEEPSEEK_URL")
BOT_NAME = os.getenv("BOT_NAME", "Джонни")
LOG_FILE = os.getenv("LOG_FILE", "dialogues.json")

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен!")
if not DEEPSEEK_CHAT_URL:
    raise ValueError("DEEPSEEK_URL не установлен!")

# ========== НАСТРОЙКИ ПОВЕДЕНИЯ ==========
MIN_TYPING_DELAY = 3
MAX_TYPING_DELAY = 8
EMOJI_CHANCE = 0.25  # 25% шанс добавить эмодзи
ANTI_SPAM_WINDOW = 10
MAX_MESSAGES_IN_WINDOW = 3

# Вежливые эмодзи
EMOJIS = ["😊", "👍", "😄", "👌", "🔥", "🤝", "✨", "🙂"]

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=TOKEN)
dp = Dispatcher()

browser = None
page = None
playwright_instance = None
deepseek_ready = False

user_last_message_time = {}
user_message_count = {}


# ========== ФУНКЦИИ ==========

def get_typing_delay(user_id: int) -> float:
    """Задержка перед ответом (человеческая)"""
    base_delay = random.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY)
    # Если флудит — отвечаем чуть медленнее
    if user_id in user_message_count:
        if user_message_count[user_id] > MAX_MESSAGES_IN_WINDOW:
            base_delay += random.uniform(1, 3)
    return base_delay


def add_gentle_emoji(text: str) -> str:
    """Иногда добавляет вежливое эмодзи в конец"""
    if random.random() > EMOJI_CHANCE:
        return text
    emoji = random.choice(EMOJIS)
    text = text.rstrip()
    if text.endswith(('!', '?', '.', ',', ';', ':')):
        return text + " " + emoji
    return text + " " + emoji


def update_spam_tracking(user_id: int):
    """Отслеживает частоту сообщений"""
    current_time = time.time()
    if user_id not in user_last_message_time:
        user_last_message_time[user_id] = current_time
        user_message_count[user_id] = 1
        return
    time_diff = current_time - user_last_message_time[user_id]
    if time_diff < ANTI_SPAM_WINDOW:
        user_message_count[user_id] = user_message_count.get(user_id, 0) + 1
    else:
        user_message_count[user_id] = 1
    user_last_message_time[user_id] = current_time


async def init_browser():
    """Запускает браузер"""
    global browser, page, playwright_instance, deepseek_ready
    print("🚀 Запуск браузера...")
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(headless=True)
    page = await browser.new_page()
    print(f"🌐 Открываю DeepSeek...")
    await page.goto(DEEPSEEK_CHAT_URL)
    await page.wait_for_timeout(5000)
    print("✅ Браузер готов")
    deepseek_ready = True


async def send_to_deepseek(message: str) -> str:
    """Отправляет сообщение в DeepSeek"""
    global page
    try:
        input_box = await page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=5000)
        await input_box.fill('')
        await input_box.fill(message)
        await input_box.press('Enter')
        await page.wait_for_timeout(3000)

        assistant_msg = await page.query_selector('[data-message-author-role="assistant"], .assistant-message')
        if not assistant_msg:
            messages = await page.query_selector_all('[class*="message"]')
            if messages:
                last = messages[-1]
                text = await last.inner_text()
                return text.strip()
            return "Не удалось получить ответ."

        text = await assistant_msg.inner_text()
        return text.strip()
    except Exception as e:
        print(f"❌ Ошибка DeepSeek: {e}")
        return "Не получилось отправить, попробуй еще раз."


def log_dialogue(user_id, username, user_message, bot_response, delay):
    """Сохраняет диалог в лог"""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []

    logs.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "user_message": user_message,
        "bot_response": bot_response,
        "delay_seconds": round(delay, 2)
    })

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(f"Привет! Я {BOT_NAME}, 34 года. Давай пообщаемся 😊")


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    """Сбрасывает контекст диалога"""
    global page
    try:
        new_chat = await page.query_selector('button:has-text("Новый чат")')
        if new_chat:
            await new_chat.click()
            await message.answer("🔄 Диалог сброшен. Начинаем заново.")
        else:
            await message.answer("Не нашел кнопку сброса, попробуй обновить страницу вручную.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@dp.message(F.text)
async def handle_message(message: Message):
    """Обрабатывает текстовые сообщения"""
    global deepseek_ready

    if not deepseek_ready:
        await message.answer("⏳ Бот загружается, подожди немного...")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user_text = message.text

    # Антиспам
    update_spam_tracking(user_id)

    # Задержка "печатания"
    delay = get_typing_delay(user_id)
    await bot.send_chat_action(user_id, "typing")
    await asyncio.sleep(delay)

    try:
        # Получаем ответ от DeepSeek
        response = await send_to_deepseek(user_text)

        # Добавляем эмодзи (иногда)
        response = add_gentle_emoji(response)

        # Логируем
        log_dialogue(user_id, username, user_text, response, delay)

        # Отправляем ответ (с разбивкой если длинный)
        if len(response) > 4096:
            for i in range(0, len(response), 4000):
                await message.answer(response[i:i + 4000])
        else:
            await message.answer(response)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await message.answer("Что-то пошло не так. Давай попробуем еще раз.")


@dp.message()
async def handle_unknown(message: Message):
    await message.answer("Напиши текстовое сообщение, я отвечу 😊")


# ========== ЗАПУСК ==========

async def main():
    print(f"🤖 Запуск {BOT_NAME}...")
    await init_browser()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())