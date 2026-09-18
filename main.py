import asyncio
import json
import logging
import os
import time
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.client.session.aiohttp import AiohttpSession

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = "8266331441:AAHFvjsCZLpR1PH7qThYxUtvF-QTfgNK9Ek"
TARGET_CHAT_ID = 478303152  # Твой Telegram ID (@Stefuck)

# Twitch credentials
TWITCH_CLIENT_ID = "lcycumen7tju9pncbzg1n7m7w8wx58"
TWITCH_CLIENT_SECRET = "y58dijr1sql7c5sgbv860mywlgx0l9"

CHECK_INTERVAL = 30  # Интервал проверки в секундах
PA_PROXY = "http://proxy.server:3128"  # Прокси PythonAnywhere
DATA_FILE = "channels.json"
# ================================================

DEFAULT_CHANNELS = {
    "twitch": ["xqc", "ohnepixel"],
    "kick": ["xqc", "ohnepixel"]
}


def load_channels():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка чтения {DATA_FILE}: {e}")
    return DEFAULT_CHANNELS.copy()


def save_channels(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения {DATA_FILE}: {e}")


channels_data = load_channels()

stream_states = {
    "twitch": {ch.lower(): False for ch in channels_data.get("twitch", [])},
    "kick": {ch.lower(): False for ch in channels_data.get("kick", [])}
}

twitch_access_token = None

bot_session = AiohttpSession(proxy=PA_PROXY)
bot = Bot(token=BOT_TOKEN, session=bot_session)
dp = Dispatcher()


async def get_twitch_token(http_session: aiohttp.ClientSession):
    global twitch_access_token
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    try:
        async with http_session.post(url, params=params, proxy=PA_PROXY) as resp:
            if resp.status == 200:
                data = await resp.json()
                twitch_access_token = data.get("access_token")
                logging.info("Twitch Access Token успешно обновлен.")
            else:
                logging.error(f"Ошибка получения токена Twitch: {resp.status}")
    except Exception as e:
        logging.error(f"Сбой запроса токена Twitch: {e}")


# ================= ПРОВЕРКА СТРИМОВ =================

async def check_twitch(http_session: aiohttp.ClientSession):
    global twitch_access_token
    twitch_list = channels_data.get("twitch", [])
    if not twitch_list:
        return

    if not twitch_access_token:
        await get_twitch_token(http_session)
        if not twitch_access_token:
            return

    url = "https://api.twitch.tv/helix/streams"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {twitch_access_token}"
    }
    params = [("user_login", ch.lower()) for ch in twitch_list]

    try:
        async with http_session.get(url, headers=headers, params=params, proxy=PA_PROXY) as resp:
            if resp.status == 401:
                await get_twitch_token(http_session)
                return

            if resp.status == 200:
                data = await resp.json()
                live_streams = {s["user_login"].lower(): s for s in data.get("data", [])}

                for channel in twitch_list:
                    ch_lower = channel.lower()
                    is_live = ch_lower in live_streams
                    was_live = stream_states["twitch"].get(ch_lower, False)

                    if is_live and not was_live:
                        stream_info = live_streams[ch_lower]
                        display_name = stream_info.get("user_name", channel)
                        title = stream_info.get("title", "Без названия")
                        game = stream_info.get("game_name", "Не указана")
                        link = f"https://twitch.tv/{channel}"

                        thumb_template = stream_info.get("thumbnail_url", "")
                        thumbnail_url = thumb_template.replace("{width}", "1280").replace("{height}", "720")
                        if thumbnail_url:
                            thumbnail_url += f"?t={int(time.time())}"

                        caption = (
                            f"🔴 **{display_name} прямо сейчас в эфире!**\n\n"
                            f"📌 **Название:** {title}\n\n"
                            f"🎮 **Категория:** {game}"
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="📺 Смотреть на Twitch", url=link)
                        ]])

                        try:
                            if thumbnail_url:
                                await bot.send_photo(TARGET_CHAT_ID, photo=thumbnail_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                            else:
                                await bot.send_message(TARGET_CHAT_ID, caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                        except Exception as e:
                            logging.error(f"Сбой отправки фото Twitch: {e}")
                            await bot.send_message(TARGET_CHAT_ID, caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

                    stream_states["twitch"][ch_lower] = is_live
    except Exception as e:
        logging.error(f"Ошибка проверки Twitch: {e}")


async def check_kick(http_session: aiohttp.ClientSession):
    kick_list = channels_data.get("kick", [])
    if not kick_list:
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    for channel in kick_list:
        ch_lower = channel.lower()
        url = f"https://kick.com/api/v1/channels/{ch_lower}"
        try:
            async with http_session.get(url, headers=headers, proxy=PA_PROXY) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    livestream = data.get("livestream")
                    is_live = livestream is not None and livestream != {}
                    was_live = stream_states["kick"].get(ch_lower, False)

                    if is_live and not was_live:
                        user_info = data.get("user", {})
                        display_name = user_info.get("username") or data.get("name") or channel

                        title = livestream.get("session_title", "Без названия")
                        category = livestream.get("categories", [{}])[0].get("name", "Не указана") if livestream.get("categories") else "Не указана"
                        link = f"https://kick.com/{channel}"

                        thumbnail_url = livestream.get("thumbnail", {}).get("url")

                        caption = (
                            f"🟢 **{display_name} прямо сейчас в эфире!**\n\n"
                            f"📌 **Название:** {title}\n\n"
                            f"🎮 **Категория:** {category}"
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🟢 Смотреть на Kick", url=link)
                        ]])

                        try:
                            if thumbnail_url:
                                await bot.send_photo(TARGET_CHAT_ID, photo=thumbnail_url, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                            else:
                                await bot.send_message(TARGET_CHAT_ID, caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                        except Exception:
                            await bot.send_message(TARGET_CHAT_ID, caption, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

                    stream_states["kick"][ch_lower] = is_live
        except Exception as e:
            logging.error(f"Ошибка проверки Kick для {channel}: {e}")


async def monitor_loop():
    async with aiohttp.ClientSession() as http_session:
        await get_twitch_token(http_session)
        while True:
            await check_twitch(http_session)
            await check_kick(http_session)
            await asyncio.sleep(CHECK_INTERVAL)


# ================= КОМАНДЫ БОТА =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **Бот-оповещатель запущен!**\n\n"
        "Доступные команды:\n"
        "• `/status` — Проверить статус отслеживаемых каналов\n"
        "• `/add <twitch|kick> <имя_канала>` — Добавить канал\n"
        "• `/remove <twitch|kick> <имя_канала>` — Удалить канал",
        parse_mode=ParseMode.MARKDOWN
    )


@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Пример использования: `/add twitch xqc` или `/add kick xqc`", parse_mode=ParseMode.MARKDOWN)
        return

    platform = args[1].lower()
    channel = args[2].lower()

    if platform not in ["twitch", "kick"]:
        await message.answer("⚠️ Платформа должна быть `twitch` или `kick`.", parse_mode=ParseMode.MARKDOWN)
        return

    if channel in channels_data[platform]:
        await message.answer(f"ℹ️ Канал `{channel}` уже есть в списке {platform.capitalize()}.", parse_mode=ParseMode.MARKDOWN)
        return

    channels_data[platform].append(channel)
    stream_states[platform][channel] = False
    save_channels(channels_data)
    await message.answer(f"✅ Канал `{channel}` добавлен в отслеживание на **{platform.capitalize()}**!", parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Пример использования: `/remove twitch xqc` или `/remove kick xqc`", parse_mode=ParseMode.MARKDOWN)
        return

    platform = args[1].lower()
    channel = args[2].lower()

    if platform not in ["twitch", "kick"]:
        await message.answer("⚠️ Платформа должна быть `twitch` или `kick`.", parse_mode=ParseMode.MARKDOWN)
        return

    if channel not in channels_data[platform]:
        await message.answer(f"ℹ️ Канала `{channel}` нет в списке {platform.capitalize()}.", parse_mode=ParseMode.MARKDOWN)
        return

    channels_data[platform].remove(channel)
    stream_states[platform].pop(channel, None)
    save_channels(channels_data)
    await message.answer(f"🗑 Канал `{channel}` удален из отслеживания на **{platform.capitalize()}**.", parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    lines = ["📊 **Текущий статус каналов:**\n"]

    lines.append("🟣 **Twitch:**")
    twitch_list = channels_data.get("twitch", [])
    if not twitch_list:
        lines.append("  _Список пуст_")
    else:
        for ch in twitch_list:
            is_live = stream_states["twitch"].get(ch.lower(), False)
            status_str = "🔴 **В эфире**" if is_live else "⚪ Офлайн"
            lines.append(f"  • `{ch}` — {status_str}")

    lines.append("\n🟢 **Kick:**")
    kick_list = channels_data.get("kick", [])
    if not kick_list:
        lines.append("  _Список пуст_")
    else:
        for ch in kick_list:
            is_live = stream_states["kick"].get(ch.lower(), False)
            status_str = "🔴 **В эфире**" if is_live else "⚪ Офлайн"
            lines.append(f"  • `{ch}` — {status_str}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(monitor_loop())
    print("Бот-оповещатель запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())