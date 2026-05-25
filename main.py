"""
Telegram бот Джонни — использует DeepSeek через Playwright
С сохранением cookies, обычный запуск (не persistent context)
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
TOKEN = "8341114630:AAGVtbQ47T9HX1YqKJ91t5xUU8ukkS6m_F8"
DEEPSEEK_CHAT_URL = "https://chat.deepseek.com/a/chat/s/61257496-cd26-4d3c-a387-79772ad68596"
BOT_NAME = "Джонни"
LOG_FILE = "dialogues.json"
COOKIES_FILE = "deepseek_cookies.json"  # файл для сохранения cookies

# ========== НАСТРОЙКИ ==========
MIN_TYPING_DELAY = 3
MAX_TYPING_DELAY = 8
EMOJI_CHANCE = 0.25
ANTI_SPAM_WINDOW = 10
MAX_MESSAGES_IN_WINDOW = 3

EMOJIS = ["😊", "👍", "😄", "👌", "🔥", "🤝", "✨", "🙂"]

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=TOKEN)
dp = Dispatcher()

browser = None
context = None
page = None
playwright_instance = None
deepseek_ready = False

user_last_message_time = {}
user_message_count = {}


# ========== ФУНКЦИИ ==========

def get_typing_delay(user_id: int) -> float:
    base_delay = random.uniform(MIN_TYPING_DELAY, MAX_TYPING_DELAY)
    if user_id in user_message_count:
        if user_message_count[user_id] > MAX_MESSAGES_IN_WINDOW:
            base_delay += random.uniform(1, 3)
    return base_delay


def add_gentle_emoji(text: str) -> str:
    if random.random() > EMOJI_CHANCE:
        return text
    emoji = random.choice(EMOJIS)
    text = text.rstrip()
    if text.endswith(('!', '?', '.', ',', ';', ':')):
        return text + " " + emoji
    return text + " " + emoji


def update_spam_tracking(user_id: int):
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


async def save_cookies():
    """Сохраняет cookies в файл"""
    global context
    try:
        if context:
            cookies = await context.cookies()
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print(f"🍪 Cookies сохранены в {COOKIES_FILE}")
    except Exception as e:
        print(f"❌ Ошибка сохранения cookies: {e}")


async def load_cookies():
    """Загружает cookies из файла в контекст"""
    global context
    if not os.path.exists(COOKIES_FILE):
        print("📭 Файл с cookies не найден, потребуется вход вручную")
        return False

    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        print(f"🍪 Cookies загружены из {COOKIES_FILE}")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки cookies: {e}")
        return False


async def init_browser():
    """Запускает браузер, загружает cookies, открывает DeepSeek"""
    global browser, context, page, playwright_instance, deepseek_ready

    print("🚀 Запуск браузера...")
    playwright_instance = await async_playwright().start()

    # Обычный запуск (не persistent)
    browser = await playwright_instance.chromium.launch(headless=False)

    # Создаем контекст (как раньше)
    context = await browser.new_context()

    # Пробуем загрузить сохраненные cookies
    await load_cookies()

    # Создаем страницу
    page = await context.new_page()

    print(f"🌐 Открываю DeepSeek: {DEEPSEEK_CHAT_URL}")
    await page.goto(DEEPSEEK_CHAT_URL)

    # Ждем загрузки страницы
    print("⏳ Жду загрузки страницы...")
    await page.wait_for_timeout(5000)

    # Проверяем, есть ли поле ввода
    try:
        input_box = await page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=10000)
        print("✅ Поле ввода найдено! Бот готов к работе.")
        deepseek_ready = True
        return
    except:
        print("⚠️ Поле ввода не найдено. Возможно, нужно войти в аккаунт.")
        print("👉 Войди в DeepSeek в открывшемся окне браузера")
        print("👉 После входа нажми Enter в консоли")

        input("Нажми Enter после входа в аккаунт...")

        # Проверяем еще раз
        try:
            input_box = await page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=10000)
            print("✅ Поле ввода найдено! Сохраняю сессию...")

            # Сохраняем cookies после успешного входа
            await save_cookies()
            print("🍪 Cookies сохранены. При следующем запуске вход не потребуется.")

            deepseek_ready = True
        except:
            print("❌ Не удалось найти поле ввода. Проверь, что ты вошел в аккаунт.")
            deepseek_ready = False


async def send_to_deepseek(message: str) -> str:
    """Отправляет сообщение в DeepSeek и возвращает ответ"""
    global page

    if not page:
        return "Ошибка: страница не инициализирована"

    try:
        # Ищем поле ввода
        input_box = await page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=30000)

        # Очищаем и вводим сообщение
        await input_box.click()
        await input_box.fill('')
        await asyncio.sleep(0.3)
        await input_box.fill(message)

        # Отправляем (Enter)
        await input_box.press('Enter')
        print(f"📤 Отправлено: {message[:50]}..." if len(message) > 50 else f"📤 Отправлено: {message}")

        # Ждем ответа
        await page.wait_for_timeout(8000)

        # Пытаемся найти ответ ассистента
        assistant_msg = await page.query_selector(
            '[data-message-author-role="assistant"], .assistant-message, [class*="assistant"]')
        if not assistant_msg:
            messages = await page.query_selector_all('[class*="message"]')
            if messages:
                last = messages[-1]
                text = await last.inner_text()
                return text.strip()
            return "Не удалось получить ответ от DeepSeek."

        text = await assistant_msg.inner_text()
        print(f"📥 Получен ответ: {text[:50]}..." if len(text) > 50 else f"📥 Получен ответ: {text}")
        return text.strip()

    except Exception as e:
        print(f"❌ Ошибка при отправке в DeepSeek: {e}")
        return "Не получилось отправить, попробуй еще раз."


def log_dialogue(user_id, username, user_message, bot_response, delay):
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
    global page
    try:
        new_chat = await page.query_selector('button:has-text("Новый чат")')
        if new_chat:
            await new_chat.click()
            await message.answer("🔄 Диалог сброшен.")
        else:
            await message.answer("Не нашел кнопку сброса.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@dp.message(F.text)
async def handle_message(message: Message):
    global deepseek_ready

    if not deepseek_ready:
        await message.answer("⏳ Бот загружается, подожди...")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user_text = message.text

    update_spam_tracking(user_id)

    delay = get_typing_delay(user_id)
    await bot.send_chat_action(user_id, "typing")
    await asyncio.sleep(delay)

    try:
        response = await send_to_deepseek(user_text)
        response = add_gentle_emoji(response)
        log_dialogue(user_id, username, user_text, response, delay)

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
    await message.answer("Напиши текстовое сообщение 😊")


# ========== ЗАПУСК ==========

async def main():
    print(f"🤖 Запуск бота {BOT_NAME}...")
    await init_browser()

    if deepseek_ready:
        print("✅ Бот готов к работе!")
    else:
        print("⚠️ Бот запущен, но DeepSeek не готов. Проверь браузер.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())