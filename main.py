# main.py
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import urllib.parse
# Temporary update-logger middleware removed due to aiogram version incompatibility.
# We'll use lightweight non-intrusive logging handlers further below if needed.

from texts import *
from admin import register_admin
from onboarding import register_onboarding
from database import Database
from keyboards import *
from states import *

BOT_TOKEN = "8104721228:AAHPnw-PHAMYMJARBvBULtm5_SeFcrhfm3g"
ADMIN_IDS = [931410785]
PLATFORM_FEE = 99
MIN_WITHDRAW = 7000

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
fallback_router = Router()

# Инициализация БД и регистрация модулей
db = Database()

# РЕГИСТРАЦИЯ АДМИНКИ И ОНБОРДИНГА
admin_router = register_admin(db, bot, ADMIN_IDS, PLATFORM_FEE)
onboarding_router = register_onboarding(db, ADMIN_IDS)

async def notify_admin_booking(event_data: dict):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                ADMIN_NEW_BOOKING.format(
                    event_title=event_data['event_title'],
                    city=event_data['city'],
                    date=event_data['date'],
                    username=event_data['username'],
                    user_id=event_data['user_id'],
                    confirmed_count=event_data['confirmed_count'],
                    max_participants=event_data['max_participants']
                )
            )
        except Exception as e:
            logging.error(f"Failed to send notification to admin {admin_id}: {e}")

async def notify_event_participants(event_id: int, new_participant_data: dict):
    try:
        participants = await db.get_all_confirmed_participants(event_id, new_participant_data['telegram_id'])
        
        event = await db.get_event_details(event_id)
        if not event:
            return
        
        event_type = event[1] or event[0]
        confirmed_count = event[12]
        
        for participant in participants:
            participant_id, username, name = participant
            try:
                await bot.send_message(
                    participant_id,
                    PARTICIPANT_NOTIFICATION.format(
                        username=new_participant_data['username'],
                        event_type=event_type,
                        confirmed_count=confirmed_count,
                        max_participants=event[5]
                    ),
                    reply_markup=get_main_menu_kb(participant_id, ADMIN_IDS) if participant_id in ADMIN_IDS else None
                )
            except Exception as e:
                logging.error(f"Failed to send notification to participant {participant_id}: {e}")
    except Exception as e:
        logging.error(f"Failed to send participant notifications: {e}")


async def notify_event_cancellation(event_id: int, cancelled_by_telegram_id: int):
    """Уведомить всех подтверждённых участников (кроме отменившего) о том, что событие отменено."""
    try:
        event = await db.get_event_details(event_id)
        if not event:
            return

        event_type = event[1] or event[0]
        date = event[3]
        time = event[4]

        participants = await db.get_all_confirmed_participants(event_id, exclude_telegram_id=cancelled_by_telegram_id)
        for p in participants:
            try:
                participant_tg, username, name = p
                await bot.send_message(
                    participant_tg,
                    f"❌ Событие отменено\n\n🎯 {event_type}\n📅 {date} {time}\n\nОрганизатор отменил событие."
                )
            except Exception as e:
                logging.error(f"Failed to notify participant {p} about cancellation: {e}")
    except Exception as e:
        logging.error(f"Failed to run cancellation notifications for event {event_id}: {e}")

async def handle_full_event(event_id: int):
    """
    Обработка полного события
    Когда событие набирает максимум участников
    """
    try:
        event = await db.get_event_details(event_id)
        if not event:
            return
        
        (event_type, custom_type, city, date, time, max_participants, 
         description, contact, status, creator_id, creator_username, 
         creator_name, confirmed_count) = event
        
        participants = await db.get_event_participants_list(event_id)
        
        # 1. Уведомление организатору
        creator_telegram_id = await db.get_creator_telegram_id(event_id)
        if creator_telegram_id:
                await bot.send_message(
                     creator_telegram_id,
                     f"""🎊 ВАУ! СОБЫТИЕ ПОЛНОСТЬЮ ЗАПОЛНЕНО!

🎯 {custom_type or event_type}
📅 {date} в {time}
👥 {confirmed_count}/{max_participants} участников

🔥 Что дальше?

1️⃣ Создай групповой чат
    • Добавь всех участников
    • Назови чат по типу события

2️⃣ Координируй
    • Уточни детали встречи
    • Ответь на вопросы
    • Поддерживай настроение!

3️⃣ Наслаждайся
    • Все оплатили участие
    • Люди ждут твоего события
    • Сделай это незабываемым!

💡 Совет: Начни диалог с приветствия и краткого плана!"""
                )
        
        # 2. Уведомление всем участникам
        for participant in participants:
            username, telegram_id, name, joined_at = participant
            if telegram_id != creator_telegram_id:
                try:
                    await bot.send_message(
                        telegram_id,
                        f"""🎉 ОТЛИЧНЫЕ НОВОСТИ!

Событие "{custom_type or event_type}" набрало полный состав!

👥 Всего участников: {confirmed_count}
📅 Дата: {date}
⏰ Время: {time}
📍 Место: {city}

🔥 Что дальше?

1. Организатор скоро создаст чат
2. Ждите приглашения в течение 24 часов
3. Подготовьтесь к встрече!

🎯 Если организатор не связался с вами до {date}, напишите ему напрямую: {contact}

💫 Желаем отличного времяпровождения!"""
                    )
                except Exception as e:
                    logging.error(f"Failed to notify participant {telegram_id}: {e}")
        
        return True
    except Exception as e:
        logging.error(f"Error in handle_full_event: {e}")
        return False

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("invite_"):
        try:
            parts = args[1].split("_")
            event_id = int(parts[1])
            inviter_id = int(parts[2]) if len(parts) > 2 else None
            
            await db.add_user(message.from_user.id, message.from_user.username)
            
            name, city, onboarded = await db.get_user_profile(message.from_user.id)
            
            if not onboarded:
                await state.update_data(inviter_id=inviter_id, invite_event_id=event_id)
                await state.set_state(OnboardingStates.NAME)
                await message.answer(
                    INVITE_WELCOME,
                    reply_markup=ReplyKeyboardRemove()
                )
                return
            else:
                event = await db.get_event_details(event_id)
                if event:
                    (event_type, custom_type, event_city, date, time, max_participants, 
                     description, contact, status, creator_id, creator_username, 
                     creator_name, confirmed_count) = event
                    
                    display_type = custom_type or event_type
                    
                    is_confirmed = await db.is_user_confirmed(event_id, message.from_user.id)
                    
                    text = INVITE_EVENT_TEXT.format(
                        event_type=display_type,
                        city=event_city,
                        date=date,
                        time=time,
                        creator=creator_name or '@' + creator_username,
                        contact=contact,
                        confirmed_count=confirmed_count,
                        max_participants=max_participants,
                        description=description
                    )
                    
                    if is_confirmed:
                        text += EVENT_ALREADY_CONFIRMED
                    else:
                        text += EVENT_JOIN_PROMPT
                    
                    await state.set_state(MainStates.VIEWING_EVENT)
                    await state.update_data(current_event_id=event_id)
                    
                    await message.answer(
                        text, 
                        reply_markup=get_event_details_kb(event_id, message.from_user.id, is_confirmed)
                    )
                else:
                    await message.answer(ERROR_EVENT_NOT_FOUND)
                return
        except Exception as e:
            logging.error(f"Error processing invite: {e}")
    
    await db.add_user(message.from_user.id, message.from_user.username)
    
    name, city, onboarded = await db.get_user_profile(message.from_user.id)
    
    logging.info(f"User {message.from_user.id} onboarded: {onboarded}")
    
    if not onboarded:
        logging.info(f"Setting state to OnboardingStates.NAME for user {message.from_user.id}")
        await state.set_state(OnboardingStates.NAME)
        current_state = await state.get_state()
        logging.info(f"State set to {current_state} for user {message.from_user.id}")
        await message.answer(
            WELCOME_ONBOARDING,
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await state.set_state(MainStates.MAIN_MENU)
        await message.answer(
            MAIN_MENU_WELCOME.format(name=name),
            reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
        )

@router.message(F.text == BTN_PROFILE)
async def my_profile(message: Message, state: FSMContext):
    user_info = await db.get_user_full_info(message.from_user.id)
    
    if not user_info:
        await message.answer(
            PROFILE_NOT_FOUND,
            reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
        )
        return
    
    name, city, username, rating, created_at, events_created, bookings_made = user_info
    
    created_date = datetime.fromisoformat(created_at.replace(' ', 'T')).strftime("%d.%m.%Y")
    
    profile_text = PROFILE_TEXT.format(
        name=name,
        city=city,
        username=username if username else 'не указан',
        rating=rating,
        events_created=events_created,
        bookings_made=bookings_made,
        created_date=created_date
    )
    
    user_events = await db.get_user_created_events(message.from_user.id)
    is_creator = len(user_events) > 0
    await state.set_state(ProfileStates.VIEWING)
    # Показываем баланс инициатора
    creator_db_id = await db.get_user_id(message.from_user.id)
    initiator_balance = 0.0
    if creator_db_id:
        initiator_balance = await db.get_initiator_balance(creator_db_id)

    profile_earnings = PROFILE_EARNINGS.format(initiator_balance=round(initiator_balance, 2))

    await message.answer(
        profile_text + "\n\n" + profile_earnings,
        reply_markup=get_profile_kb(message.from_user.id, ADMIN_IDS, is_creator)
    )

@router.message(F.text == BTN_HELP)
async def how_to_use(message: Message, state: FSMContext):
    await state.set_state(MainStates.MAIN_MENU)
    await message.answer(
        HELP_TEXT,
        reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
    )

@router.message(F.text == BTN_CANCEL)
async def cancel_anywhere(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(MainStates.MAIN_MENU)
    await message.answer(
        CANCELLED_ACTION,
        reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
    )

@router.message(F.text == BTN_BACK)
async def go_back(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    # Если мы в админских состояниях - НИЧЕГО НЕ ДЕЛАЕМ
    if current_state and "AdminStates" in current_state:
        # Админка работает через callback-кнопки, текстовые кнопки игнорируем
        await message.answer("В админке используйте кнопки меню")
        return
    
    if current_state == CreateEventStates.TYPE:
        await state.set_state(MainStates.MAIN_MENU)
        await message.answer(BACK_TO_MAIN, reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS))
    
    elif current_state == CreateEventStates.TYPE_OTHER:
        # Возврат к началу создания события — показываем единый экран step_1
        await state.set_state(CreateEventStates.step_1)
        await send_create_intro(message, state)
    
    elif current_state == CreateEventStates.DATE:
        await state.set_state(CreateEventStates.step_1)
        await send_create_intro(message, state)
    
    elif current_state == CreateEventStates.TIME:
        await state.set_state(CreateEventStates.DATE)
        await message.answer(
            "[Создание события 2/7]\n\nВведите дату в формате ДД.ММ.ГГГГ\nНапример: 25.12.2024",
            reply_markup=get_back_cancel_kb()
        )
    
    elif current_state == CreateEventStates.MAX_PARTICIPANTS:
        await state.set_state(CreateEventStates.TIME)
        await message.answer(
            "[Создание события 3/7]\n\nВведите время в формате ЧЧ:ММ\nНапример: 19:00",
            reply_markup=get_back_cancel_kb()
        )
    
    elif current_state == CreateEventStates.DESCRIPTION:
        await state.set_state(CreateEventStates.MAX_PARTICIPANTS)
        await message.answer(
            "[Создание события 4/7]\n\nВведите максимальное количество участников:",
            reply_markup=get_back_cancel_kb()
        )
    
    elif current_state == CreateEventStates.CONTACT:
        await state.set_state(CreateEventStates.DESCRIPTION)
        await message.answer(
            "[Создание события 5/7]\n\n📝 Введите описание события (обязательно):",
            reply_markup=get_back_cancel_kb()
        )
    
    elif current_state == CreateEventStates.CONFIRMATION:
        await state.set_state(CreateEventStates.CONTACT)
        await message.answer(
            "[Создание события 6/7]\n\n📞 Введите ваш контакт для связи с участников:",
            reply_markup=get_back_cancel_kb()
        )
    
    # Обработка возврата из профиля
    elif current_state == ProfileStates.VIEWING:
        await state.set_state(MainStates.MAIN_MENU)
        await message.answer(BACK_TO_MAIN, reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS))
    
    elif current_state == ProfileStates.MY_EVENTS:
        await state.set_state(ProfileStates.VIEWING)
        await my_profile(message, state)
    
    elif current_state == ProfileStates.MY_BOOKINGS:
        await state.set_state(ProfileStates.VIEWING)
        await my_profile(message, state)
    
    else:
        await state.set_state(MainStates.MAIN_MENU)
        await message.answer(BACK_TO_MAIN, reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS))

@router.message(F.text == BTN_CREATE)
async def start_create_event(message: Message, state: FSMContext):
    name, city, onboarded = await db.get_user_profile(message.from_user.id)
    
    if not onboarded:
        await message.answer("Пожалуйста, сначала пройди онбординг — нажми /start, и всё будет готово.")
        return
    
    await state.update_data(city=city)
    # Переводим пользователя в шаг 1 создания события.
    await state.set_state(CreateEventStates.step_1)
    # Большой вводный текст отправляется только в обработчике CreateEventStates.step_1
    await send_create_intro(message, state)


async def send_create_intro(message: Message, state: FSMContext):
    """Отправляет единый расширенный экран начала создания события
    и переводит сессию в состояние выбора типа (TYPE)."""
    await message.answer(CREATE_EVENT_START, reply_markup=get_event_types_kb())
    # Готовы принять выбор типа
    await state.set_state(CreateEventStates.TYPE)

@router.message(CreateEventStates.TYPE)
async def process_event_type(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    if message.text not in ["🎉 Туса", "🎳 Страйкбол", "🔫 Пейнтбол", "🎯 Другое"]:
        await message.answer(
            "Пожалуйста, выбери тип из списка — нажми одну из кнопок:",
            reply_markup=get_event_types_kb()
        )
        return
    
    if message.text == "🎯 Другое":
        await state.set_state(CreateEventStates.TYPE_OTHER)
        await message.answer(CREATE_EVENT_TYPE_OTHER, reply_markup=get_back_cancel_kb())
        return
    
    event_type = message.text[2:]
    await state.update_data(type=event_type, custom_type=None)
    await state.set_state(CreateEventStates.DATE)
    
    await message.answer(
        CREATE_EVENT_DATE.format(event_type=event_type),
        reply_markup=get_back_cancel_kb()
    )

@router.message(CreateEventStates.TYPE_OTHER)
async def process_event_type_other(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    try:
        custom_type = message.text.strip()
        
        if len(custom_type) < 3:
            await message.answer(
                "Название получилось коротким — напиши, пожалуйста, чуть длиннее (минимум 3 символа).\nПримеры: Танцы, Волейбол, Пикник.\n\nПопробуй ещё раз:",
                reply_markup=get_back_cancel_kb()
            )
            return
        
        if len(custom_type) > 50:
            await message.answer(
                "Название слишком длинное — попробуй короче (до 50 символов).",
                reply_markup=get_back_cancel_kb()
            )
            return
        
        await state.update_data(type="Другое", custom_type=custom_type)
        await state.set_state(CreateEventStates.DATE)
        
        await message.answer(
            CREATE_EVENT_DATE.format(event_type=custom_type),
            reply_markup=get_back_cancel_kb()
        )
    except Exception as e:
        logging.error(f"Error in process_event_type_other: {e}")
        await message.answer(
            "Упс — что-то пошло не так. Попробуй ещё раз, пожалуйста.",
            reply_markup=get_back_cancel_kb()
        )


@router.message(CreateEventStates.DATE)
async def process_event_date(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    date_str = message.text.strip()
    
    try:
        event_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now().date()
        
        if event_date < today:
            await message.answer(
                ERROR_PAST_DATE,
                reply_markup=get_back_cancel_kb()
            )
            return
    except ValueError:
        await message.answer(
            ERROR_INVALID_DATE,
            reply_markup=get_back_cancel_kb()
        )
        return
    
    await state.update_data(date=date_str)
    await state.set_state(CreateEventStates.TIME)
    
    await message.answer(
        CREATE_EVENT_TIME.format(date=date_str),
        reply_markup=get_back_cancel_kb()
    )

@router.message(CreateEventStates.TIME)
async def process_event_time(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    try:
        time_str = message.text.strip()
        
        datetime.strptime(time_str, "%H:%M")
        
        await state.update_data(time=time_str)
        await state.set_state(CreateEventStates.MAX_PARTICIPANTS)
        
        await message.answer(
            CREATE_EVENT_MAX_PARTICIPANTS.format(time=time_str),
            reply_markup=get_back_cancel_kb()
        )
    except ValueError:
        await message.answer(
            ERROR_INVALID_TIME,
            reply_markup=get_back_cancel_kb()
        )
    except Exception as e:
        logging.error(f"Error in process_event_time: {e}")
        await message.answer(
            "Упс — что-то пошло не так. Попробуй ещё раз, пожалуйста.",
            reply_markup=get_back_cancel_kb()
        )

@router.message(CreateEventStates.MAX_PARTICIPANTS)
async def process_max_participants(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    try:
        max_participants = int(message.text)
        if max_participants < 2:
            await message.answer(
                "Нужно минимум 2 участника — введи число не меньше 2, например: 10",
                reply_markup=get_back_cancel_kb()
            )
            return
        if max_participants > 1000:
            await message.answer(
                "Слишком большой лимит — максимум 1000 участников. Введи меньше, пожалуйста.",
                reply_markup=get_back_cancel_kb()
            )
            return
    except ValueError:
        await message.answer(
            "Похоже, это не число — введи, пожалуйста, цифрами, например: 10",
            reply_markup=get_back_cancel_kb()
        )
        return
    
    await state.update_data(max_participants=max_participants)
    await state.set_state(CreateEventStates.DESCRIPTION)
    
    await message.answer(
        CREATE_EVENT_DESCRIPTION.format(max_participants=max_participants),
        reply_markup=get_back_cancel_kb()
    )

@router.message(CreateEventStates.DESCRIPTION)
async def process_description(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    description = message.text.strip()
    
    if len(description) < 10:
        await message.answer(
            ERROR_DESCRIPTION_TOO_SHORT,
            reply_markup=get_back_cancel_kb()
        )
        return
    
    if len(description) > 500:
        await message.answer(
            "Описание слишком длинное — сократи, пожалуйста, до 500 символов.",
            reply_markup=get_back_cancel_kb()
        )
        return
    
    await state.update_data(description=description)
    await state.set_state(CreateEventStates.CONTACT)
    
    await message.answer(
        CREATE_EVENT_CONTACT.format(description_preview=description[:100]),
        reply_markup=get_back_cancel_kb()
    )

@router.message(CreateEventStates.CONTACT)
async def process_contact(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    try:
        contact = message.text.strip()
        
        if len(contact) < 3:
            await message.answer(
                ERROR_CONTACT_TOO_SHORT,
                reply_markup=get_back_cancel_kb()
            )
            return
        
        if len(contact) > 100:
            await message.answer(
                "Контакт получился слишком длинным — сократи до 100 символов, пожалуйста.",
                reply_markup=get_back_cancel_kb()
            )
            return
        
        await state.update_data(contact=contact)
        await state.set_state(CreateEventStates.CONFIRMATION)
        
        data = await state.get_data()
        event_type = data.get('custom_type') or data['type']
        
        text = CREATE_EVENT_CONFIRMATION.format(
            event_type=event_type,
            city=data['city'],
            date=data['date'],
            time=data['time'],
            max_participants=data['max_participants'],
            description_preview=data['description'][:100],
            contact=contact
        )
        
        await message.answer(text, reply_markup=get_confirm_kb())
    except Exception as e:
        logging.error(f"Error in process_contact: {e}")
        await message.answer(
            "Упс — что-то пошло не так. Попробуй ещё раз, пожалуйста.",
            reply_markup=get_back_cancel_kb()
        )
        return

@router.message(CreateEventStates.CONFIRMATION)
async def process_confirmation(message: Message, state: FSMContext):
    if message.text == BTN_CANCEL:
        await cancel_anywhere(message, state)
        return
    if message.text == BTN_BACK:
        await go_back(message, state)
        return
    
    if message.text == BTN_CONFIRM:
        try:
            data = await state.get_data()
            
            event_id = await db.create_event(data, message.from_user.id)
            
            if not event_id:
                await message.answer(
                    "Не получилось создать событие — попробуй позже, пожалуйста.",
                    reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
                )
                await state.clear()
                return
            
            invite_link = f"https://t.me/{bot._me.username}?start=invite_{event_id}_{message.from_user.id}"
            
            event_type = data.get('custom_type') or data['type']
            
            text = EVENT_CREATED.format(
                event_type=event_type,
                city=data['city'],
                date=data['date'],
                time=data['time'],
                max_participants=data['max_participants'],
                description_preview=data['description'][:200],
                contact=data['contact']
            )
            
            await state.clear()
            await state.set_state(MainStates.MAIN_MENU)
            await message.answer(text, reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS))
            
            instructions = EVENT_NEXT_STEPS.format(invite_link=invite_link)
            
            await message.answer(instructions)
            
            logging.info(f"Event created: ID={event_id}, creator={message.from_user.id}, type={event_type}")
        except Exception as e:
            logging.error(f"Error creating event: {e}", exc_info=True)
            await message.answer(
                "Не удалось создать событие. Попробуй позже или напиши в поддержку.",
                reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
            )
            await state.clear()
        
    elif message.text == BTN_EDIT:
        # Вернуться к началу создания — единый экран
        await state.set_state(CreateEventStates.step_1)
        await send_create_intro(message, state)
    else:
        await message.answer(
            "Выбери, пожалуйста, вариант:",
            reply_markup=get_confirm_kb()
        )

@router.message(F.text == BTN_FIND)
async def start_search(message: Message, state: FSMContext):
    name, city, onboarded = await db.get_user_profile(message.from_user.id)
    
    if not onboarded:
        await message.answer("Пожалуйста, сначала пройди онбординг — нажми /start, и всё будет готово.")
        return
    # Показываем экран выбора города для поиска (не меняем profile.city)
    await state.set_state(SearchEventsStates.CHOOSE_CITY)
    await message.answer(
        "📍 В каком городе ищем события?",
        reply_markup=get_search_city_choice_kb(city)
    )


@router.callback_query(F.data == CB_SEARCH_USE_MY_CITY)
async def search_use_my_city(callback: CallbackQuery, state: FSMContext):
    # Используем город из профиля, не меняя профиль
    name, city, onboarded = await db.get_user_profile(callback.from_user.id)
    if not city:
        await callback.answer("В вашем профиле не указан город.", show_alert=True)
        return

    events = await db.get_events_by_city(city)
    # сортируем по популярности (confirmed_count DESC)
    events_sorted = sorted(events, key=lambda e: e[4] or 0, reverse=True)
    if not events_sorted:
        await callback.message.edit_text(SEARCH_NO_EVENTS.format(city=city))
        await callback.answer()
        await state.set_state(MainStates.MAIN_MENU)
        return

    # Сохраняем список id в FSM
    events_ids = [e[0] for e in events_sorted]
    await state.update_data(events_ids=events_ids, current_index=0, search_city=city)
    await state.set_state(SearchEventsStates.SELECT_EVENT)

    # Показать премиум-карточку первого события
    first_event = await db.get_event_full_details(events_ids[0])
    text = render_premium_card_text(first_event)
    kb = get_premium_event_kb(events_ids[0], 0, len(events_ids), callback.from_user.id, await db.is_user_confirmed(events_ids[0], callback.from_user.id), urllib.parse.quote_plus(city))

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == CB_SEARCH_CHOOSE_CITY)
async def search_choose_city(callback: CallbackQuery, state: FSMContext):
    # Открываем UI выбора города (повторно используем клавиатуру онбординга)
    await state.set_state(SearchEventsStates.CHOOSE_CITY)
    await callback.message.edit_text(
        "Выберите город:",
        reply_markup=get_cities_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == CB_ONBOARDING_CANCEL)
async def search_cancel_city(callback: CallbackQuery, state: FSMContext):
    """Обработка нажатия 'Отмена' в экранe выбора города при поиске — возврат в главное меню."""
    current_state = await state.get_state()
    if current_state == SearchEventsStates.CHOOSE_CITY.state:
        await state.clear()
        await state.set_state(MainStates.MAIN_MENU)
        try:
            await callback.message.edit_text(BACK_TO_MAIN)
        except Exception:
            pass
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_main_menu_kb(callback.from_user.id, ADMIN_IDS)
        )
        await callback.answer()
        return


@router.callback_query(F.data.startswith(CB_CITY_PAGE))
async def search_city_page(callback: CallbackQuery, state: FSMContext):
    # пагинация списка городов в режиме выбора города для поиска
    try:
        page = int(callback.data.split(CB_CITY_PAGE, 1)[1])
        await callback.message.edit_reply_markup(reply_markup=get_cities_keyboard(page))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith(CB_CITY_SELECT))
async def search_set_city(callback: CallbackQuery, state: FSMContext):
    # Выбрали конкретный город в режиме поиска — не записываем в профиль
    try:
        city = callback.data.split(CB_CITY_SELECT, 1)[1]
    except Exception:
        await callback.answer()
        return

    events = await db.get_events_by_city(city)
    events_sorted = sorted(events, key=lambda e: e[4] or 0, reverse=True)
    if not events_sorted:
        await callback.message.edit_text(SEARCH_NO_EVENTS.format(city=city))
        await callback.answer()
        await state.set_state(MainStates.MAIN_MENU)
        return

    events_ids = [e[0] for e in events_sorted]
    await state.update_data(events_ids=events_ids, current_index=0, search_city=city)
    await state.set_state(SearchEventsStates.SELECT_EVENT)

    first_event = await db.get_event_full_details(events_ids[0])
    text = render_premium_card_text(first_event)
    kb = get_premium_event_kb(events_ids[0], 0, len(events_ids), callback.from_user.id, await db.is_user_confirmed(events_ids[0], callback.from_user.id), urllib.parse.quote_plus(city))

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_EVENT_NAV_PREV))
async def event_nav_prev(callback: CallbackQuery, state: FSMContext):
    # data format: event:nav:prev:{current_index}:{city_key}
    try:
        rest = callback.data.split(CB_EVENT_NAV_PREV, 1)[1]
        idx_str, city_key = rest.split(":", 1)
        current_index = int(idx_str)
    except Exception:
        await callback.answer()
        return

    data = await state.get_data()
    events_ids = data.get('events_ids') or []
    if not events_ids:
        await callback.answer("Сессия поиска устарела.", show_alert=True)
        return

    new_index = max(0, current_index - 1)
    event_id = events_ids[new_index]
    event = await db.get_event_full_details(event_id)
    text = render_premium_card_text(event)
    kb = get_premium_event_kb(event_id, new_index, len(events_ids), callback.from_user.id, await db.is_user_confirmed(event_id, callback.from_user.id), city_key)

    await state.update_data(current_index=new_index)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_EVENT_NAV_NEXT))
async def event_nav_next(callback: CallbackQuery, state: FSMContext):
    try:
        rest = callback.data.split(CB_EVENT_NAV_NEXT, 1)[1]
        idx_str, city_key = rest.split(":", 1)
        current_index = int(idx_str)
    except Exception:
        await callback.answer()
        return

    data = await state.get_data()
    events_ids = data.get('events_ids') or []
    if not events_ids:
        await callback.answer("Сессия поиска устарела.", show_alert=True)
        return

    new_index = min(len(events_ids) - 1, current_index + 1)
    event_id = events_ids[new_index]
    event = await db.get_event_full_details(event_id)
    text = render_premium_card_text(event)
    kb = get_premium_event_kb(event_id, new_index, len(events_ids), callback.from_user.id, await db.is_user_confirmed(event_id, callback.from_user.id), city_key)

    await state.update_data(current_index=new_index)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_EVENT_SHOW))
async def event_show_details(callback: CallbackQuery, state: FSMContext):
    try:
        event_id = int(callback.data.split(CB_EVENT_SHOW, 1)[1])
    except Exception:
        await callback.answer()
        return

    # Покажем детали события через уже существующий handler: используем edit_text с get_event_details_kb
    event = await db.get_event_details(event_id)
    if not event:
        await callback.answer(ERROR_EVENT_NOT_FOUND)
        return

    (event_type, custom_type, city, date, time, max_participants, 
     description, contact, status, creator_id, creator_username, 
     creator_name, confirmed_count) = event

    display_type = custom_type or event_type
    is_confirmed = await db.is_user_confirmed(event_id, callback.from_user.id)

    text = EVENT_DETAILS.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        creator=creator_name or '@' + creator_username,
        contact=contact,
        confirmed_count=confirmed_count,
        max_participants=max_participants,
        status=status,
        description=description,
        user_status=EVENT_ALREADY_CONFIRMED if is_confirmed else EVENT_JOIN_PROMPT
    )

    await state.set_state(MainStates.VIEWING_EVENT)
    await state.update_data(current_event_id=event_id)
    await callback.message.edit_text(text, reply_markup=get_event_details_kb(event_id, callback.from_user.id, is_confirmed))
    await callback.answer()


def render_premium_card_text(event_full):
    """Форматирование текста премиум-карточки из get_event_full_details row."""
    if not event_full:
        return "Событие не найдено."

    # event_full columns per db.get_event_full_details
    (eid, etype, custom_type, city, date, time, max_participants, description, contact, status, created_at, creator_telegram_id, creator_name, creator_username, confirmed_count, total_participants) = event_full

    display_type = custom_type or etype

    # human-readable date
    try:
        event_date = datetime.strptime(date, "%d.%m.%Y").date()
        today = datetime.now().date()
        if event_date == today:
            date_str = f"Сегодня в {time}"
        else:
            # простой формат: DD MMMM • HH:MM
            months = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
            day = int(date.split('.')[0])
            month = months[int(date.split('.')[1]) - 1]
            date_str = f"{day} {month} • {time}"
    except Exception:
        date_str = f"{date} {time}"

    confirmed = confirmed_count or 0
    max_p = max_participants or 0

    badge = ""
    try:
        fill_ratio = (confirmed / max_p) if max_p > 0 else 0
        if fill_ratio >= 0.9 and confirmed >= 5:
            badge = " 🔥 Популярно"
        elif fill_ratio >= 0.75:
            badge = " ⏳ Почти фулл"
    except Exception:
        badge = ""

    short_desc = (description or "").strip().split('\n')[:4]
    short_desc = '\n'.join(short_desc)

    creator = creator_name or (('@' + creator_username) if creator_username else 'не указан')

    parts = [f"🎉 {display_type}{badge}", f"🏙 {city}", f"📅 {date_str}", f"👥 {confirmed} из {max_p}", "", short_desc]
    if contact:
        parts.append(f"📞 Контакт: {contact}")

    return "\n".join(parts)

@router.callback_query(F.data.startswith(CB_EVENT_VIEW))
async def view_event_details(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split(CB_EVENT_VIEW, 1)[1])
    
    event = await db.get_event_details(event_id)
    
    if not event:
        await callback.answer(ERROR_EVENT_NOT_FOUND)
        await state.set_state(MainStates.MAIN_MENU)
        await callback.message.answer(
            ERROR_EVENT_NOT_FOUND + ". Вернитесь в главное меню:",
            reply_markup=get_main_menu_kb(callback.from_user.id, ADMIN_IDS)
        )
        return
    
    (event_type, custom_type, city, date, time, max_participants, 
     description, contact, status, creator_id, creator_username, 
     creator_name, confirmed_count) = event
    
    display_type = custom_type or event_type

    # Сохраняем контекст возврата в FSM, если он есть (premium flow)
    data = await state.get_data()
    if data.get('events_ids'):
        # Если пользователь пришёл из премиум-потока — сохраняем контекст
        await state.update_data(return_context={
            'city': data.get('search_city'),
            'current_index': data.get('current_index', 0),
            'sort': 'confirmed_desc',
            'source': 'premium_events_list'
        })

    await state.set_state(MainStates.VIEWING_EVENT)
    await state.update_data(current_event_id=event_id)
    
    is_confirmed = await db.is_user_confirmed(event_id, callback.from_user.id)
    
    text = EVENT_DETAILS.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        creator=creator_name or '@' + creator_username,
        contact=contact,
        confirmed_count=confirmed_count,
        max_participants=max_participants,
        status=status,
        description=description,
        user_status=EVENT_ALREADY_CONFIRMED if is_confirmed else EVENT_JOIN_PROMPT
    )
    
    await callback.message.edit_text(
        text, 
        reply_markup=get_event_details_kb(event_id, callback.from_user.id, is_confirmed)
    )
    await callback.answer()


@router.callback_query(F.data == CB_BACK_TO_EVENTS)
async def back_to_events_list(callback: CallbackQuery, state: FSMContext):
    """Возврат к премиум-списку событий по сохранённому в FSM контексту.
    Если контекста нет — показываем экран выбора города (fallback)."""
    data = await state.get_data()
    ctx = data.get('return_context')

    if ctx and ctx.get('source') == 'premium_events_list' and ctx.get('city'):
        city = ctx.get('city')
        current_index = int(ctx.get('current_index', 0))

        events = await db.get_events_by_city(city)
        events_sorted = sorted(events, key=lambda e: e[4] or 0, reverse=True)
        if not events_sorted:
            # Нет событий в городе — вернём на выбор города
            await state.set_state(SearchEventsStates.CHOOSE_CITY)
            await callback.message.edit_text("📍 В каком городе ищем события?", reply_markup=get_search_city_choice_kb(city))
            await callback.answer()
            return

        events_ids = [e[0] for e in events_sorted]
        # Нормализуем индекс
        if current_index < 0 or current_index >= len(events_ids):
            current_index = 0

        await state.update_data(events_ids=events_ids, current_index=current_index, search_city=city)
        await state.set_state(SearchEventsStates.SELECT_EVENT)

        event_id = events_ids[current_index]
        event_full = await db.get_event_full_details(event_id)
        text = render_premium_card_text(event_full)
        kb = get_premium_event_kb(event_id, current_index, len(events_ids), callback.from_user.id, await db.is_user_confirmed(event_id, callback.from_user.id), urllib.parse.quote_plus(city))

        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
        return

    # Фоллбек: показываем выбор города
    await state.set_state(SearchEventsStates.CHOOSE_CITY)
    await callback.message.edit_text("📍 В каком городе ищем события?", reply_markup=get_search_city_choice_kb())
    await callback.answer()

@router.callback_query(F.data.startswith(CB_EVENT_JOIN))
async def join_event_start(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split(CB_EVENT_JOIN, 1)[1])
    
    event = await db.get_event_details(event_id)
    
    if not event:
        await callback.answer(ERROR_EVENT_NOT_FOUND)
        return
    
    (event_type, custom_type, city, date, time, max_participants, 
     description, contact, status, creator_id, creator_username, 
     creator_name, confirmed_count) = event
    
    display_type = custom_type or event_type
    
    await state.update_data(event_id=event_id, join_event_id=event_id)
    await state.set_state(JoinEventStates.PAYMENT_INFO)
    
    text = BOOKING_PAYMENT_INFO.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        fee=PLATFORM_FEE
    )
    
    await callback.message.edit_text(text, reply_markup=get_payment_kb(event_id))
    await callback.answer()

@router.callback_query(F.data.startswith(CB_EVENT_BACK))
async def back_from_payment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("event_id")
    
    if not event_id:
        try:
            event_id = int(callback.data.split(CB_EVENT_BACK, 1)[1])
        except Exception:
            await callback.answer("Не получилось вернуться — попробуй ещё раз.")
            return
    
    event = await db.get_event_details(event_id)
    if not event:
        await callback.answer(ERROR_EVENT_NOT_FOUND)
        return
    
    (event_type, custom_type, city, date, time, max_participants, 
     description, contact, status, creator_id, creator_username, 
     creator_name, confirmed_count) = event
    
    display_type = custom_type or event_type
    is_confirmed = await db.is_user_confirmed(event_id, callback.from_user.id)
    
    text = EVENT_DETAILS.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        creator=creator_name or '@' + creator_username,
        contact=contact,
        confirmed_count=confirmed_count,
        max_participants=max_participants,
        status=status,
        description=description,
        user_status=EVENT_ALREADY_CONFIRMED if is_confirmed else EVENT_JOIN_PROMPT
    )
    
    await state.set_state(MainStates.VIEWING_EVENT)
    await state.update_data(event_id=event_id)
    
    await callback.message.edit_text(
        text, 
        reply_markup=get_event_details_kb(event_id, callback.from_user.id, is_confirmed)
    )
    await callback.answer()

@router.callback_query(F.data.startswith(CB_EVENT_PAID))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split(CB_EVENT_PAID, 1)[1])
    
    success, message_text = await db.add_participant(event_id, callback.from_user.id)
    
    if not success:
        await callback.answer(f"❌ {message_text}")
        return
    
    await db.confirm_participant(event_id, callback.from_user.id)
    
    name, city, onboarded = await db.get_user_profile(callback.from_user.id)
    participant_name = name or callback.from_user.first_name or "Пользователь"
    participant_username = callback.from_user.username or "нет username"
    
    event = await db.get_event_details(event_id)
    if event:
        (event_type, custom_type, event_city, date, time, max_participants, 
         description, contact, status, creator_id, creator_username, 
         creator_name, confirmed_count) = event
        
        display_type = custom_type or event_type
        
        await notify_admin_booking({
            'event_title': display_type,
            'city': event_city,
            'date': f"{date} {time}",
            'username': participant_username,
            'user_id': callback.from_user.id,
            'confirmed_count': confirmed_count,
            'max_participants': max_participants
        })
        
        await notify_event_participants(event_id, {
            'telegram_id': callback.from_user.id,
            'username': participant_username,
            'name': participant_name
        })
        
        # Проверяем, заполнилось ли событие
        if confirmed_count >= max_participants:
            await handle_full_event(event_id)
        
        text = PAYMENT_CONFIRMED.format(
            event_type=display_type,
            city=event_city,
            date=date,
            time=time,
            contact=contact
        )
        
        await state.update_data(event_id=event_id)
        await state.set_state(MainStates.VIEWING_EVENT)
        
        buttons = [
            [InlineKeyboardButton(text="📲 Пригласить друга", callback_data=f"{CB_EVENT_INVITE}{event_id}:{callback.from_user.id}")],
            [InlineKeyboardButton(text="📌 К деталям события", callback_data=f"{CB_EVENT_BACK}{event_id}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data=CB_NAV_BACK_TO_MAIN)]
        ]
        
        await callback.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith(CB_EVENT_INVITE))
async def invite_friend(callback: CallbackQuery):
    rest = callback.data.split(CB_EVENT_INVITE, 1)[1]
    if ":" in rest:
        event_id_str, inviter_id_str = rest.split(":", 1)
    elif "_" in rest:
        parts = rest.split("_")
        event_id_str = parts[0]
        inviter_id_str = parts[1] if len(parts) > 1 else str(callback.from_user.id)
    else:
        event_id_str = rest
        inviter_id_str = str(callback.from_user.id)

    event_id = int(event_id_str)
    inviter_id = int(inviter_id_str)
    invite_link = f"https://t.me/{bot._me.username}?start=invite_{event_id}_{inviter_id}"
    
    await callback.message.answer(
        INVITE_LINK_TEXT.format(invite_link=invite_link)
    )
    await callback.answer()


# ----- Отмена события (инициатор) -----
@router.callback_query(F.data.startswith("cancel_event:"))
async def cancel_event_start(callback: CallbackQuery):
    """Показывает подтверждение отмены события инициатору."""
    try:
        event_id = int(callback.data.split("cancel_event:", 1)[1])
    except Exception:
        await callback.answer("Это событие нельзя отменить.", show_alert=True)
        return

    event = await db.get_event_details(event_id)
    if not event:
        await callback.answer("Это событие нельзя отменить.", show_alert=True)
        return

    # event tuple: type, custom_type, city, date, time, max_participants, description, contact, status, creator_id, ...
    status = event[8]
    creator_id = event[9]

    # Проверка прав: только создатель (по user id) может отменять
    user_id = await db.get_user_id(callback.from_user.id)
    if not user_id or user_id != creator_id or status != 'ACTIVE':
        await callback.answer("Это событие нельзя отменить.", show_alert=True)
        return

    # Показываем подтверждение (не меняем FSM)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"confirm_cancel:{event_id}"),
         InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_event:{event_id}")]
    ])

    await callback.message.edit_text(
        "Ты точно хочешь отменить событие?\nУчастники больше не смогут записаться.",
        reply_markup=confirm_kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_event:"))
async def back_to_event(callback: CallbackQuery):
    """Возврат к деталям/управлению своего события (не трогаем FSM)."""
    try:
        event_id = int(callback.data.split("back_to_event:", 1)[1])
    except Exception:
        await callback.answer("Ошибка навигации", show_alert=False)
        return

    event = await db.get_event_details(event_id)
    if not event:
        await callback.answer("Это событие нельзя просмотреть.", show_alert=True)
        return

    (event_type, custom_type, city, date, time, max_participants,
     description, contact, status, creator_id) = event[:10]

    display_type = custom_type or event_type

    # Формируем текст управления событием (показываем статус)
    status_text = '✅ Активно' if status == 'ACTIVE' else '❌ Отменено'
    bottom_text = ""

    text = EVENT_MANAGEMENT_DETAILS.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        status=status_text,
        confirmed_count=await db.get_event_participants_count(event_id),
        max_participants=max_participants,
        contact=contact,
        description=description,
        bottom_text=bottom_text
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к моим событиям", callback_data=CB_NAV_BACK_TO_MY_EVENTS)]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel:"))
async def confirm_cancel(callback: CallbackQuery):
    """Подтверждение отмены — обновляем статус в базе без удаления и без изменения FSM."""
    try:
        event_id = int(callback.data.split("confirm_cancel:", 1)[1])
    except Exception:
        await callback.answer("Это событие нельзя отменить.", show_alert=True)
        return

    success = await db.cancel_event(event_id, callback.from_user.id)
    if not success:
        await callback.answer("Это событие нельзя отменить.", show_alert=True)
        return

    # Уведомляем участников (кроме инициатора)
    await notify_event_cancellation(event_id, callback.from_user.id)

    # Получаем обновлённые детали и показываем статус отмены
    event = await db.get_event_details(event_id)
    if not event:
        await callback.answer("Это событие нельзя показать.", show_alert=True)
        return

    (event_type, custom_type, city, date, time, max_participants,
     description, contact, status, creator_id) = event[:10]

    display_type = custom_type or event_type

    text = f"Событие отменено ❌\n\n🎯 {display_type}\n🏙 {city}\n📅 {date} {time}\n\nСтатус: ❌ Отменено"

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к моим событиям", callback_data=CB_NAV_BACK_TO_MY_EVENTS)]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == CB_PROFILE_MY_BOOKINGS)
async def show_my_bookings(callback: CallbackQuery, state: FSMContext):
    bookings = await db.get_user_bookings(callback.from_user.id)
    
    if not bookings:
        await callback.message.edit_text(
            MY_BOOKINGS_EMPTY_WITH_SUGGESTION,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Найти события", callback_data=CB_NAV_BACK_TO_MAIN)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_NAV_BACK_TO_PROFILE)]
            ])
        )
        await callback.answer()
        return
    
    bookings_text = MY_BOOKINGS_LIST
    
    for i, booking in enumerate(bookings[:10], 1):
        event_id, event_type, city, date_time, booking_date = booking
        booking_dt = datetime.fromisoformat(booking_date.replace(' ', 'T'))
        formatted_date = booking_dt.strftime("%d.%m.%Y")
        
        bookings_text += (
            f"{i}. {event_type}\n"
            f"   🏙 {city} | 📅 {date_time}\n"
            f"   🕐 Забронировано: {formatted_date}\n\n"
        )
    
    if len(bookings) > 10:
        bookings_text += f"\n... и ещё {len(bookings) - 10} бронирований"
    
    await state.set_state(ProfileStates.MY_BOOKINGS)
    await callback.message.edit_text(
        bookings_text,
        reply_markup=get_my_bookings_kb(bookings[:10])
    )
    await callback.answer()

@router.callback_query(F.data == CB_PROFILE_MY_EVENTS)
async def show_my_events(callback: CallbackQuery, state: FSMContext):
    events = await db.get_user_created_events(callback.from_user.id)
    
    if not events:
        await callback.message.edit_text(
            MY_EVENTS_EMPTY_WITH_SUGGESTION,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать событие", callback_data=CB_NAV_BACK_TO_MAIN)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_NAV_BACK_TO_PROFILE)]
            ])
        )
        await callback.answer()
        return
    
    events_text = MY_EVENTS_LIST
    active_count = 0
    
    for event in events:
        event_id, event_type, city, date_time, status, participants_count, max_participants = event
        if status == 'ACTIVE':
            active_count += 1
            status_text = "✅ Активно"
        else:
            status_text = "❌ Неактивно"
        
        events_text += (
            f"{event_type}\n"
            f"🏙 {city} | 📅 {date_time}\n"
            f"👥 {participants_count}/{max_participants} участников\n"
            f"{status_text}\n\n"
        )
    
    events_text = MY_EVENTS_LIST.format(active_count=active_count) + events_text[24:]
    
    await state.set_state(ProfileStates.MY_EVENTS)
    await callback.message.edit_text(
        events_text,
        reply_markup=get_my_events_kb(events)
    )
    await callback.answer()

@router.callback_query(F.data.startswith(CB_EVENT_MY))
async def show_my_event_details(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split(CB_EVENT_MY, 1)[1])
    
    event = await db.get_event_details(event_id)
    
    if not event:
        await callback.answer(ERROR_EVENT_NOT_FOUND)
        return
    
    (event_type, custom_type, city, date, time, max_participants, 
     description, contact, status, creator_id, creator_username, 
     creator_name, confirmed_count) = event
    
    display_type = custom_type or event_type
    
    participants = await db.get_event_participants_list(event_id)
    
    bottom_text = f"Уже забронировали: {len(participants)} участник(ов)\n" if participants else ""
    
    text = EVENT_MANAGEMENT_DETAILS.format(
        event_type=display_type,
        city=city,
        date=date,
        time=time,
        status='✅ Активно' if status == 'ACTIVE' else '❌ Неактивно',
        confirmed_count=confirmed_count,
        max_participants=max_participants,
        contact=contact,
        description=description,
        bottom_text=bottom_text
    )
    
    await state.set_state(ProfileStates.MY_EVENTS)
    await callback.message.edit_text(
        text,
        reply_markup=get_event_manage_kb(event_id)
    )
    await callback.answer()


@router.callback_query(F.data == "withdraw:request")
async def withdraw_request(callback: CallbackQuery):
    """Начало flow запроса вывода: проверяем баланс и даём инструкцию по отправке реквизитов (/withdraw)."""
    # получить баланс
    db_user_id = await db.get_user_id(callback.from_user.id)
    if not db_user_id:
        await callback.answer("Профиль не найден.", show_alert=True)
        return

    balance = await db.get_initiator_balance(db_user_id)
    if balance < MIN_WITHDRAW:
        await callback.answer(WITHDRAW_MIN_ERROR.format(min_withdraw=MIN_WITHDRAW, balance=round(balance,2)), show_alert=True)
        return

    await callback.message.answer(
        f"Ваш баланс: {round(balance,2)} ₽. Чтобы создать заявку, отправьте команду:\n/withdraw <сумма> <реквизиты>\nПример: /withdraw {int(balance)} Сбербанк 410..."
    )
    await callback.answer()


@router.message(Command('withdraw'))
async def handle_withdraw_command(message: Message):
    """Обрабатывает команду /withdraw <amount> <contact>. Если amount пропущен — пытается вывести весь баланс."""
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: /withdraw <сумма> <реквизиты>")
        return

    # определяем сумму и контакт
    amount = None
    contact = None
    if len(parts) == 2:
        # возможно передали только реквизиты — используем весь баланс
        contact = parts[1]
    else:
        # parts[1] может быть суммой
        try:
            amount = float(parts[1])
            contact = parts[2] if len(parts) > 2 else ''
        except ValueError:
            # нет суммы — берем весь баланс, parts[1] это контакт
            contact = message.text[len('/withdraw '):]

    db_user_id = await db.get_user_id(message.from_user.id)
    if not db_user_id:
        await message.answer("Профиль не найден.")
        return

    balance = await db.get_initiator_balance(db_user_id)
    if amount is None:
        amount = round(balance, 2)

    if amount <= 0 or amount > balance:
        await message.answer(f"Неверная сумма. Доступно: {round(balance,2)} ₽")
        return

    req_id = await db.create_withdraw_request(db_user_id, amount, contact)
    if req_id == -1:
        await message.answer("Ошибка: недостаточно средств.")
        return

    await message.answer(WITHDRAW_REQUEST_CREATED_USER.format(amount=round(amount,2)))

    # уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Выполнить", callback_data=f"withdraw:process:{req_id}"), InlineKeyboardButton(text="Отклонить", callback_data=f"withdraw:reject:{req_id}")]
            ])
            await message.bot.send_message(admin_id, WITHDRAW_REQUEST_ADMIN_NOTIFY.format(id=req_id, user=message.from_user.id, amount=round(amount,2), contact=contact), reply_markup=kb)
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id} about withdrawal {req_id}: {e}")

@router.callback_query(F.data.startswith(CB_EVENT_PARTICIPANTS))
async def show_event_participants(callback: CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split(CB_EVENT_PARTICIPANTS, 1)[1])
    
    participants = await db.get_event_participants_list(event_id)
    
    if not participants:
        await callback.message.edit_text(
            EVENT_PARTICIPANTS_EMPTY,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{CB_EVENT_MY}{event_id}")]
            ])
        )
        await callback.answer()
        return
    
    participants_text = EVENT_PARTICIPANTS_LIST
    
    for i, participant in enumerate(participants, 1):
        username, telegram_id, name, joined_at = participant
        display_name = f"@{username}" if username else name or f"ID: {telegram_id}"
        join_date = datetime.fromisoformat(joined_at.replace(' ', 'T')).strftime("%d.%m")
        
        participants_text += f"{i}. {display_name}\n   🆔 {telegram_id} | 📅 {join_date}\n"
    
    participants_text += f"\nВсего: {len(participants)} участник(ов)"
    
    await state.set_state(ProfileStates.MY_EVENTS)
    await callback.message.edit_text(
        participants_text,
        reply_markup=get_participants_kb(event_id, participants)
    )
    await callback.answer()

@router.callback_query(F.data.startswith(CB_USER_INFO))
async def show_user_info(callback: CallbackQuery):
    try:
        telegram_id = int(callback.data.split(CB_USER_INFO, 1)[1])
    except Exception:
        await callback.answer("Неверный идентификатор пользователя.")
        return

    info = await db.get_user_full_info(telegram_id)
    if not info:
        await callback.answer(ERROR_USER_NOT_FOUND)
        return

    name, city, username, rating, created_at, events_created, bookings_made = info
    created_date = datetime.fromisoformat(created_at.replace(' ', 'T')).strftime("%d.%m.%Y")

    text = USER_INFO.format(
        name=name,
        city=city,
        username=username if username else 'не указан',
        rating=rating,
        events_created=events_created,
        bookings_made=bookings_made,
        created_date=created_date
    )

    await callback.message.answer(text)
    await callback.answer()

# ХЭНДЛЕРЫ НАВИГАЦИИ - БЕЗ СОСТОЯНИЙ, ЧТОБЫ РАБОТАЛИ ВЕЗДЕ
@router.callback_query(F.data == CB_NAV_BACK_TO_MAIN)
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MainStates.MAIN_MENU)
    await callback.message.edit_text(BACK_TO_MAIN)
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=get_main_menu_kb(callback.from_user.id, ADMIN_IDS)
    )
    await callback.answer()

@router.callback_query(F.data == CB_NAV_BACK_TO_PROFILE)
async def back_to_profile(callback: CallbackQuery, state: FSMContext):
    user_info = await db.get_user_full_info(callback.from_user.id)
    
    if not user_info:
        await callback.answer("Профиль не найдена.")
        return
    
    name, city, username, rating, created_at, events_created, bookings_made = user_info
    created_date = datetime.fromisoformat(created_at.replace(' ', 'T')).strftime("%d.%m.%Y")
    
    profile_text = PROFILE_TEXT.format(
        name=name,
        city=city,
        username=username if username else 'не указан',
        rating=rating,
        events_created=events_created,
        bookings_made=bookings_made,
        created_date=created_date
    )
    
    user_events = await db.get_user_created_events(callback.from_user.id)
    is_creator = len(user_events) > 0
    # Показываем баланс инициатора
    creator_db_id = await db.get_user_id(callback.from_user.id)
    initiator_balance = 0.0
    if creator_db_id:
        initiator_balance = await db.get_initiator_balance(creator_db_id)

    profile_earnings = PROFILE_EARNINGS.format(initiator_balance=round(initiator_balance, 2))
    profile_text = profile_text + "\n\n" + profile_earnings

    
    await state.set_state(ProfileStates.VIEWING)
    await callback.message.edit_text(
        profile_text,
        reply_markup=get_profile_kb(callback.from_user.id, ADMIN_IDS, is_creator)
    )
    await callback.answer()

@router.callback_query(F.data == CB_NAV_BACK_TO_SEARCH)
async def back_to_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchEventsStates.SELECT_EVENT)
    
    name, city, onboarded = await db.get_user_profile(callback.from_user.id)
    events = await db.get_events_by_city(city)
    
    if events:
        text = SEARCH_FOUND_EVENTS.format(city=city, count=len(events)) + "\n\nВыберите событие:"
        await callback.message.edit_text(text, reply_markup=get_event_list_kb(events))
    else:
        await callback.message.edit_text(SEARCH_NO_EVENTS.format(city=city))
        await callback.message.answer(
            BACK_TO_MAIN,
            reply_markup=get_main_menu_kb(callback.from_user.id, ADMIN_IDS)
        )
        await state.set_state(MainStates.MAIN_MENU)
    
    await callback.answer()

@router.callback_query(F.data == CB_NAV_BACK_TO_MY_EVENTS)
async def back_to_my_events(callback: CallbackQuery, state: FSMContext):
    events = await db.get_user_created_events(callback.from_user.id)
    
    if not events:
        await callback.message.edit_text(
            MY_EVENTS_EMPTY_WITH_SUGGESTION,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_NAV_BACK_TO_PROFILE)]
            ])
        )
        await callback.answer()
        return
    
    events_text = MY_EVENTS_LIST
    active_count = 0
    
    for event in events:
        event_id, event_type, city, date_time, status, participants_count, max_participants = event
        if status == 'ACTIVE':
            active_count += 1
        
        events_text += (
            f"{event_type}\n"
            f"🏙 {city} | 📅 {date_time}\n"
            f"👥 {participants_count}/{max_participants} участников\n"
            f"{ '✅ Активно' if status == 'ACTIVE' else '❌ Неактивно'}\n\n"
        )
    
    events_text = MY_EVENTS_LIST.format(active_count=active_count) + events_text[24:]
    
    await state.set_state(ProfileStates.MY_EVENTS)
    await callback.message.edit_text(
        events_text,
        reply_markup=get_my_events_kb(events)
    )
    await callback.answer()

@router.callback_query(F.data == CB_NAV_BACK_TO_MY_BOOKINGS)
async def back_to_my_bookings(callback: CallbackQuery, state: FSMContext):
    bookings = await db.get_user_bookings(callback.from_user.id)
    
    if not bookings:
        await callback.message.edit_text(
            MY_BOOKINGS_EMPTY_WITH_SUGGESTION,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_NAV_BACK_TO_PROFILE)]
            ])
        )
        await callback.answer()
        return
    
    bookings_text = MY_BOOKINGS_LIST
    
    for i, booking in enumerate(bookings[:10], 1):
        event_id, event_type, city, date_time, booking_date = booking
        booking_dt = datetime.fromisoformat(booking_date.replace(' ', 'T'))
        formatted_date = booking_dt.strftime("%d.%m.%Y")
        
        bookings_text += (
            f"{i}. {event_type}\n"
            f"   🏙 {city} | 📅 {date_time}\n"
            f"   🕐 Забронировано: {formatted_date}\n\n"
        )
    
    if len(bookings) > 10:
        bookings_text += f"\n... и ещё {len(bookings) - 10} бронирований"
    
    await state.set_state(ProfileStates.MY_BOOKINGS)
    await callback.message.edit_text(
        bookings_text,
        reply_markup=get_my_bookings_kb(bookings[:10])
    )
    await callback.answer()

@router.callback_query(F.data.startswith(CB_BOOKING_CANCEL))
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены бронирования"""
    try:
        event_id = int(callback.data.split(CB_BOOKING_CANCEL, 1)[1])
        
        # Получаем информацию о событии
        event = await db.get_event_details(event_id)
        
        if not event:
            await callback.message.edit_text(
                BOOKING_NOT_FOUND,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data=CB_NAV_BACK_TO_PROFILE)]
                ])
            )
            await callback.answer(BOOKING_NOT_FOUND, show_alert=True)
            return
        
        # Пытаемся отменить бронирование
        success = await db.cancel_booking(callback.from_user.id, event_id)
        
        if success:
            (event_type, custom_type, city, date, time, max_participants, 
             description, contact, status, creator_id, creator_username, 
             creator_name, confirmed_count) = event
            
            display_type = custom_type or event_type
            date_time = f"{date} {time}"
            
            # Показываем сообщение об успехе
            await callback.message.edit_text(
                BOOKING_CANCEL_SUCCESS.format(
                    event_type=display_type,
                    city=city,
                    date_time=date_time
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Мои бронирования", callback_data=CB_PROFILE_MY_BOOKINGS)],
                    [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data=CB_NAV_BACK_TO_PROFILE)]
                ])
            )
            
            logging.info(f"User {callback.from_user.id} cancelled booking for event {event_id}")
            await callback.answer("✅ Бронирование отменено!", show_alert=False)
        else:
            await callback.message.edit_text(
                BOOKING_NOT_FOUND,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Мои бронирования", callback_data=CB_PROFILE_MY_BOOKINGS)],
                    [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data=CB_NAV_BACK_TO_PROFILE)]
                ])
            )
            await callback.answer(BOOKING_NOT_FOUND, show_alert=True)
    
    except Exception as e:
        logging.error(f"Error cancelling booking: {e}", exc_info=True)
        await callback.message.edit_text(
            BOOKING_CANCEL_ERROR,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Мои бронирования", callback_data=CB_PROFILE_MY_BOOKINGS)],
                [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data=CB_NAV_BACK_TO_PROFILE)]
            ])
        )
        await callback.answer(BOOKING_CANCEL_ERROR, show_alert=True)

# ============================================================
# FALLBACK ROUTER HANDLERS
# ============================================================
# Fallback ТОЛЬКО для неизвестного текста
# НЕ должен перехватывать:
# - команды (/start и т.д.)
# - callback_query (inline кнопки)
# - текстовые кнопки (BTN_*)
# - FSM обработчики
# ============================================================

@fallback_router.message(StateFilter(default_state))
async def fallback_text_no_state(message: Message):
    """Fallback для свободного текста БЕЗ состояния"""
    try:
        await message.answer(
            FALLBACK_MESSAGE,
            reply_markup=get_main_menu_kb(message.from_user.id, ADMIN_IDS)
        )
    except Exception as e:
        logging.error(f"Error in fallback_text_no_state: {e}")

@fallback_router.callback_query()
async def callback_fallback(callback: CallbackQuery, state: FSMContext):
    # Неадресованные callback'и — показываем мягкий фоллбек
    try:
        await callback.message.edit_text(FALLBACK_MESSAGE)
    except Exception:
        pass
    await callback.answer()

# ============================================================
# ВКЛЮЧЕНИЕ РОУТЕРОВ В ПРАВИЛЬНОМ ПОРЯДКЕ
# ============================================================
# Порядок КРИТИЧЕСКИ ВАЖЕН:
# 1. router - основная логика (команды, кнопки, callbacks)
# 2. admin_router - админка
# 3. onboarding_router - онбординг
# 4. fallback_router - ВСЕГДА ПОСЛЕДНИЙ (ловит неизвестный текст)
# ============================================================

dp.include_router(router)
dp.include_router(admin_router)
dp.include_router(onboarding_router)
dp.include_router(fallback_router)

async def main():
    await db.init_db()
    
    # ВКЛЮЧАЕМ ОТЛАДОЧНОЕ ЛОГИРОВАНИЕ
    logging.getLogger('aiogram').setLevel(logging.DEBUG)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
