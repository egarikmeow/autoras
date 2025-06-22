import asyncio  
import json
import os
import random
import aiofiles
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import ChatWriteForbiddenError, SessionPasswordNeededError

API_TOKEN = '7762245807:AAH_4SIIHqqDKugyvkTZzQUyMBoMC8P5c_4'
TESTER_ID = 8188636934
TELEGRAM_API_ID = 24144091
TELEGRAM_API_HASH = '35f8ffb23ce7378da704a39810962c61'

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

client = TelegramClient('session_name', TELEGRAM_API_ID, TELEGRAM_API_HASH)

DATA_FILE = 'user_data.json'

def load_user_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

all_users_data = load_user_data()

def get_user_config(user_id: int):
    uid = str(user_id)
    if uid not in all_users_data:
        all_users_data[uid] = {
            'frequency': 12,
            'group_links': [],          # format: ["group_link"] или ["group_link|topic_id"]
            'randomizer': {'enabled': False, 'value': 0},
            'running': False,
            # новое поле для работы с фото в настройках
            'photo_path': None,
            'message': '',
            'forward_from_chat': None,
            'forward_msg_id': None
        }
        save_user_data(all_users_data)
    return all_users_data[uid]

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

class SpamStates(StatesGroup):
    waiting_for_frequency = State()
    waiting_for_message = State()
    waiting_for_group = State()
    waiting_for_random_value = State()
    waiting_for_topic_id = State()  # Новый стейт для айди топика

# Новый стейт для выбора действия с фото в сообщении
class MessagePhotoActionStates(StatesGroup):
    waiting_for_photo_action = State()

# Функции клавиатур

def main_menu(user_id):
    user_config = get_user_config(user_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Частота", callback_data="set_freq"),
         InlineKeyboardButton(text="Сообщение", callback_data="set_msg")],
        [InlineKeyboardButton(text="Рандомайзер", callback_data="random_menu"),
         InlineKeyboardButton(text="Группы", callback_data="group_menu")],
        [InlineKeyboardButton(text="Запустить" if not user_config['running'] else "Остановить", callback_data="toggle_spam")],
        [InlineKeyboardButton(text="Войти в Телеграм", callback_data="login")]
    ])

def randomizer_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Включить/Выключить", callback_data="toggle_random"),
         InlineKeyboardButton(text="Настроить", callback_data="set_random")],
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])

def group_menu(user_id):
    user_config = get_user_config(user_id)
    buttons = []
    for i, group in enumerate(user_config['group_links']):
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить {group}", callback_data=f"del_group_{i}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить группу", callback_data="add_group")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])

def photo_action_menu(photo_exists: bool):
    if photo_exists:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Удалить фото", callback_data="del_photo"),
             InlineKeyboardButton(text="Назад", callback_data="back")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить фото", callback_data="add_photo"),
             InlineKeyboardButton(text="Назад", callback_data="back")]
        ])

# Старт бота
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id != TESTER_ID:
        return await message.answer("❌ Нет доступа")
    await message.answer("Привет, это бот для авто рассылки", reply_markup=main_menu(message.from_user.id))

# Обработка callback query
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != TESTER_ID:
        return await callback.answer("Нет доступа", show_alert=True)

    user_id = callback.from_user.id
    user_config = get_user_config(user_id)
    data = callback.data
    try:
        await callback.message.delete()
    except:
        pass

    if data == "login":
        await callback.message.answer("Введите номер телефона в формате +79991234567:", reply_markup=back_button())
        await state.set_state(AuthStates.waiting_for_phone)

    elif data == "set_freq":
        await callback.message.answer("Введите частоту (12–120 сек):", reply_markup=back_button())
        await state.set_state(SpamStates.waiting_for_frequency)

    elif data == "set_msg":
        # При входе показываем кнопки добавить фото / удалить фото + назад в зависимости от наличия фото
        keyboard = photo_action_menu(bool(user_config.get('photo_path')))
        await callback.message.answer(
            "Введите сообщение для рассылки (просто напишите текст, или выберите действие с фото):",
            reply_markup=keyboard)
        await state.set_state(SpamStates.waiting_for_message)

    elif data == "add_photo":
        await callback.message.answer("Отправьте фото для рассылки:", reply_markup=back_button())
        await state.set_state(MessagePhotoActionStates.waiting_for_photo_action)

    elif data == "del_photo":
        if user_config.get('photo_path'):
            try:
                os.remove(user_config['photo_path'])
            except:
                pass
            user_config['photo_path'] = None
            save_user_data(all_users_data)
            await callback.message.answer("✅ Фото удалено.", reply_markup=main_menu(user_id))
        else:
            await callback.message.answer("Фото отсутствует.", reply_markup=main_menu(user_id))
        await state.clear()

    elif data == "random_menu":
        await callback.message.answer("Меню рандомайзера", reply_markup=randomizer_menu())

    elif data == "toggle_random":
        user_config['randomizer']['enabled'] = not user_config['randomizer']['enabled']
        save_user_data(all_users_data)
        await callback.message.answer(
            f"Рандомайзер {'включён' if user_config['randomizer']['enabled'] else 'выключен'}",
            reply_markup=randomizer_menu())

    elif data == "set_random":
        await callback.message.answer("Введите значение от 1 до 100:", reply_markup=back_button())
        await state.set_state(SpamStates.waiting_for_random_value)

    elif data == "back":
        await callback.message.answer("Назад", reply_markup=main_menu(user_id))
        await state.clear()

    elif data == "group_menu":
        await callback.message.answer("Управление группами:", reply_markup=group_menu(user_id))

    elif data == "add_group":
        await callback.message.answer("Вставьте ссылку на группу:", reply_markup=back_button())
        await state.set_state(SpamStates.waiting_for_group)

    elif data.startswith("del_group_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(user_config['group_links']):
            removed = user_config['group_links'].pop(idx)
            save_user_data(all_users_data)
            await callback.message.answer(f"✅ Удалена группа: {removed}", reply_markup=group_menu(user_id))
        else:
            await callback.message.answer("❗ Неверный индекс группы", reply_markup=group_menu(user_id))

    elif data == "toggle_spam":
        if user_config['running']:
            user_config['running'] = False
            save_user_data(all_users_data)
            await callback.message.answer("⛔️ Рассылка остановлена", reply_markup=main_menu(user_id))
        else:
            if not user_config['group_links'] or (not user_config.get('message') and not (user_config.get('forward_from_chat') and user_config.get('forward_msg_id')) and not user_config.get('photo_path')):
                await callback.message.answer("❌ Убедитесь, что заданы группы и сообщение.", reply_markup=main_menu(user_id))
                return
            if not client.is_connected():
                await callback.message.answer("❌ Телеграм клиент не подключен. Попробуйте войти через меню.", reply_markup=main_menu(user_id))
                return
            if not await client.is_user_authorized():
                await callback.message.answer("❌ Телеграм клиент не авторизован. Войдите через меню.", reply_markup=main_menu(user_id))
                return
            user_config['running'] = True
            save_user_data(all_users_data)
            await callback.message.answer("✅ Рассылка запущена", reply_markup=main_menu(user_id))
            asyncio.create_task(spammer(user_id))

# Обработка фото при выборе добавить фото
@dp.message(MessagePhotoActionStates.waiting_for_photo_action)
async def handle_photo_action(message: types.Message, state: FSMContext):
    user_config = get_user_config(message.from_user.id)
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.")
        return
    photo = message.photo[-1]
    file_id = photo.file_id
    file_info = await bot.get_file(file_id)
    file_path = f'temp/{file_info.file_unique_id}.jpg'

    os.makedirs('temp', exist_ok=True)

    file_bytes = await bot.download_file(file_info.file_path)

    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(file_bytes)

    user_config['photo_path'] = file_path
    user_config['message'] = message.caption or ""
    user_config['forward_from_chat'] = None
    user_config['forward_msg_id'] = None
    save_user_data(all_users_data)

    await message.answer("✅ Фото добавлено и сохранено для рассылки.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# Обработка текста/фото при настройке сообщения (если пользователь не нажимал кнопки)
@dp.message(SpamStates.waiting_for_message)
async def set_message(message: types.Message, state: FSMContext):
    user_config = get_user_config(message.from_user.id)

    if message.photo:
        # Если фото пришло без нажатия кнопок - просто сохраняем фото и текст, как раньше
        photo = message.photo[-1]
        file_id = photo.file_id
        file_info = await bot.get_file(file_id)
        file_path = f'temp/{file_info.file_unique_id}.jpg'

        os.makedirs('temp', exist_ok=True)

        file_bytes = await bot.download_file(file_info.file_path)

        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_bytes)

        user_config['photo_path'] = file_path
        user_config['message'] = message.caption or ""

        user_config['forward_from_chat'] = None
        user_config['forward_msg_id'] = None
        save_user_data(all_users_data)
        await message.answer("✅ Фото с текстом установлены для рассылки.", reply_markup=main_menu(message.from_user.id))

    elif message.forward_from_chat or message.forward_from:
        chat = message.forward_from_chat or message.forward_from
        user_config['forward_from_chat'] = getattr(chat, 'id', None)
        user_config['forward_msg_id'] = message.message_id
        user_config['photo_path'] = None
        user_config['message'] = ""
        save_user_data(all_users_data)
        await message.answer("✅ Сообщение для пересылки установлено (пересылка).", reply_markup=main_menu(message.from_user.id))

    else:
        user_config['message'] = message.text or ""
        user_config['photo_path'] = None
        user_config['forward_from_chat'] = None
        user_config['forward_msg_id'] = None
        save_user_data(all_users_data)
        await message.answer("✅ Текст сообщения установлен.", reply_markup=main_menu(message.from_user.id))

    await state.clear()

@dp.message(SpamStates.waiting_for_frequency)
async def set_frequency(message: types.Message, state: FSMContext):
    user_config = get_user_config(message.from_user.id)
    try:
        val = int(message.text)
        if 12 <= val <= 120:
            user_config['frequency'] = val
            save_user_data(all_users_data)
            await message.answer(f"✅ Частота установлена: {val} сек.", reply_markup=main_menu(message.from_user.id))
            await state.clear()
        else:
            await message.answer("❗ Введите число от 12 до 120.", reply_markup=back_button())
    except:
        await message.answer("❗ Некорректное значение.", reply_markup=back_button())

@dp.message(SpamStates.waiting_for_group)
async def set_group(message: types.Message, state: FSMContext):
    user_config = get_user_config(message.from_user.id)
    group_link = message.text.strip()
    if group_link not in user_config['group_links']:
        user_config['group_links'].append(group_link)
        save_user_data(all_users_data)
        await message.answer(f"✅ Группа добавлена: {group_link}", reply_markup=group_menu(message.from_user.id))
    else:
        await message.answer("❗ Эта группа уже добавлена.", reply_markup=group_menu(message.from_user.id))
    await state.clear()

@dp.message(SpamStates.waiting_for_random_value)
async def set_random_value(message: types.Message, state: FSMContext):
    user_config = get_user_config(message.from_user.id)
    try:
        val = int(message.text)
        if 1 <= val <= 100:
            user_config['randomizer']['value'] = val
            save_user_data(all_users_data)
            await message.answer(f"✅ Рандом настроен на {val}", reply_markup=randomizer_menu())
            await state.clear()
        else:
            await message.answer("❗ Введите число от 1 до 100.", reply_markup=back_button())
    except:
        await message.answer("❗ Некорректное значение.", reply_markup=back_button())

async def spammer(user_id):
    user_config = get_user_config(user_id)
    base_freq = user_config['frequency']
    rand_enabled = user_config['randomizer']['enabled']
    rand_value = user_config['randomizer']['value']
    groups = user_config['group_links']

    async def spam_to_group(entry):
        if '|' in entry:
            group_link, topic_id = entry.split('|', 1)
            topic_id = int(topic_id.strip())
        else:
            group_link = entry.strip()
            topic_id = None

        while user_config['running']:
            try:
                entity = await client.get_entity(group_link)

                if user_config.get('forward_from_chat') and user_config.get('forward_msg_id'):
                    msg_to_forward = await client.get_messages(user_config['forward_from_chat'], ids=user_config['forward_msg_id'])
                    await client.send_message(entity=entity, message=msg_to_forward,
                                              reply_to=topic_id if topic_id else None)

                elif user_config.get('photo_path'):
                    await client.send_file(
                        entity=entity,
                        file=user_config['photo_path'],
                        caption=user_config.get('message', ''),
                        reply_to=topic_id if topic_id else None
                    )
                else:
                    await client.send_message(
                        entity=entity,
                        message=user_config.get('message', ''),
                        reply_to=topic_id if topic_id else None
                    )

            except ChatWriteForbiddenError:
                await bot.send_message(TESTER_ID, f"❌ Нет прав писать в {group_link}")
                user_config['running'] = False
                save_user_data(all_users_data)
                return
            except Exception as e:
                await bot.send_message(TESTER_ID, f"⚠️ Ошибка в {group_link}: {e}")
                user_config['running'] = False
                save_user_data(all_users_data)
                return

            delay = base_freq
            if rand_enabled:
                deviation = (rand_value / 100) * base_freq
                delay = int(random.uniform(base_freq - deviation, base_freq + deviation))
            delay = max(12, min(120, delay))
            await asyncio.sleep(delay)

    tasks = [asyncio.create_task(spam_to_group(entry)) for entry in groups]

    await asyncio.gather(*tasks)

async def on_startup():
    await client.connect()
    if await client.is_user_authorized():
        print("Telethon: сессия найдена, клиент авторизован")
    else:
        print("Telethon: сессия не авторизована, необходимо войти через бота")

async def start_webserver():
    port = int(os.getenv("PORT", 8000))

    async def handle(request):
        return web.Response(text="OK")

    app = web.Application()
    app.add_routes([web.get("/", handle)])

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"HTTP сервер запущен на порту {port}")

async def main():
    await on_startup()
    webserver_task = asyncio.create_task(start_webserver())  # запускаем веб-сервер параллельно
    await dp.start_polling(bot)
    webserver_task.cancel()
    try:
        await webserver_task
    except asyncio.CancelledError:
        pass

if __name__ == '__main__':
    print("Бот запущен")
    asyncio.run(main())
