# keyboards.py
"""
Все клавиатуры и кнопки бота
"""

from datetime import datetime
from aiogram.types import (
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)

from texts import *
try:
    from cities import CITIES
except ImportError:
    CITIES = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск"]

# === CALLBACK DATA PREFIXES ===
CB_CITY_SELECT = "city:select:"
CB_CITY_PAGE = "city:page:"
CB_SEARCH_USE_MY_CITY = "search:use_my_city"
CB_SEARCH_CHOOSE_CITY = "search:choose_city"
CB_SEARCH_SET_CITY = "search:set_city:"
CB_EVENT_NAV_PREV = "event:nav:prev:"
CB_EVENT_NAV_NEXT = "event:nav:next:"
CB_EVENT_SHOW = "event:show:"
CB_ONBOARDING_CANCEL = "onboarding:cancel"
CB_EVENT_VIEW = "event:view:"
CB_EVENT_JOIN = "event:join:"
CB_EVENT_PAID = "event:paid:"
CB_EVENT_BACK = "event:back:"
CB_EVENT_INVITE = "event:invite:"
CB_EVENT_MY = "event:my:"
CB_EVENT_PARTICIPANTS = "event:participants:"
CB_BOOKING_CANCEL = "booking:cancel:"
CB_PROFILE_MY_BOOKINGS = "profile:my_bookings"
CB_PROFILE_MY_EVENTS = "profile:my_events"
CB_NAV_BACK_TO_MAIN = "nav:back_to_main"
CB_NAV_BACK_TO_PROFILE = "nav:back_to_profile"
CB_NAV_BACK_TO_MY_EVENTS = "nav:back_to_my_events"
CB_NAV_BACK_TO_SEARCH = "nav:back_to_search"
CB_NAV_BACK_TO_MY_BOOKINGS = "nav:back_to_my_bookings"
CB_USER_INFO = "user:info:"
CB_BACK_TO_EVENTS = "event:back_to_list"
CB_CREATE_FORMAT = "cat:"
CB_CREATE_TYPE = "type:"

# Mapping of type slugs to display names per format
TYPE_MAPPING = {
    'active': [
        ('paintball','Пейнтбол'), ('strikeball','Страйкбол'), ('lasertag','Лазертаг'), ('football','Футбол'), ('basketball','Баскетбол'),
        ('volleyball','Волейбол'), ('bowling','Боулинг'), ('karting','Картинг'), ('quest_offline','Квест (офлайн)'), ('other_active','Другое активное')
    ],
    'party': [
        ('party','Вечеринка'), ('birthday','День рождения'), ('bar','Бар'), ('club','Клуб'), ('karaoke','Караоке'), ('concert','Концерт / лайв'),
        ('festival','Фестиваль'), ('thematic_party','Тематическая тусовка'), ('meetup','Meetup / встреча'), ('other_party','Другое событие')
    ],
    'esport': [
        ('pubg_mobile','PUBG Mobile'), ('mobile_legends','Mobile Legends'), ('cs2_valorant','CS2 / Valorant'), ('dota2','Dota 2'), ('fifa','FIFA / EA FC'),
        ('fortnite','Fortnite'), ('warzone','Warzone'), ('other_tournament','Другое (турнир)')
    ],
    'other': [
        ('lecture','Лекция'), ('masterclass','Мастер-класс'), ('presentation','Презентация'), ('trip','Совместная поездка'), ('walk','Прогулка'), ('networking','Нетворкинг'), ('other','Другое')
    ]
}

def get_type_display(slug: str):
    """Возвращает кортеж (format_key, display_name) для данного slug, или (None, slug) если не найдено."""
    for fmt, items in TYPE_MAPPING.items():
        for s, disp in items:
            if s == slug:
                return fmt, disp
    return None, slug

# === ОБЩИЕ КЛАВИАТУРЫ ===
def get_main_menu_kb(telegram_id, admin_ids):
    """Главное меню"""
    items = [
        KeyboardButton(text=BTN_FIND),
        KeyboardButton(text=BTN_CREATE),
        KeyboardButton(text=BTN_PROFILE),
        KeyboardButton(text=BTN_HELP)
    ]

    keyboard = []
    row = []
    for btn in items:
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_back_cancel_kb():
    """Клавиатура с кнопками Назад и Отмена"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_CANCEL)]
        ],
        resize_keyboard=True
    )

# === КЛАВИАТУРЫ ОНБОРДИНГА ===
def get_cities_keyboard(page=0, items_per_page=8):
    """Клавиатура выбора города с пагинацией"""
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    cities_slice = CITIES[start_idx:end_idx]
    
    buttons = []
    row = []
    for i, city in enumerate(cities_slice):
        idx = start_idx + i
        row.append(InlineKeyboardButton(text=city, callback_data=f"{CB_CITY_SELECT}{idx}"))
        if i % 2 == 1:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{CB_CITY_PAGE}{page-1}"))
    if end_idx < len(CITIES):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"{CB_CITY_PAGE}{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text=BTN_CANCEL, callback_data=CB_ONBOARDING_CANCEL)])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# === КЛАВИАТУРЫ СОЗДАНИЯ СОБЫТИЯ ===
def get_event_types_kb():
    """Выбор типа события"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎉 Туса\nВечеринка / тусовка"), KeyboardButton(text="🎳 Страйкбол\nКомандная игра")],
            [KeyboardButton(text="🔫 Пейнтбол\nКомандная стрельба"), KeyboardButton(text="🎯 Другое\nВвести свой тип")],
            [KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_CANCEL)]
        ],
        resize_keyboard=True
    )


# === КЛАВИАТУРЫ НОВОГО ПОТОКА СОЗДАНИЯ ===
def get_create_format_kb():
    """Inline keyboard выбора формата (категории) события"""
    buttons = [
        [InlineKeyboardButton(text="🏃‍♂️ Активные игры", callback_data=f"{CB_CREATE_FORMAT}active")],
        [InlineKeyboardButton(text="🎉 Вечеринки и тусовки", callback_data=f"{CB_CREATE_FORMAT}party")],
        [InlineKeyboardButton(text="🎮 Киберспорт и турниры", callback_data=f"{CB_CREATE_FORMAT}esport")],
        [InlineKeyboardButton(text="📚 Другое", callback_data=f"{CB_CREATE_FORMAT}other")],
        [InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_MAIN)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_types_kb_for_format(format_key: str):
    """Возвращает inline-клавиатуру типов для заданной категории format_key."""
    types = TYPE_MAPPING.get(format_key, [])
    rows = []
    seen = set()
    for slug, disp in types:
        cb = f"{CB_CREATE_TYPE}{slug}"
        if cb in seen:
            continue
        seen.add(cb)
        rows.append([InlineKeyboardButton(text=disp, callback_data=cb)])

    # Кнопка назад к выбору формата
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{CB_CREATE_FORMAT}BACK")])
    # Отмена — в главное меню
    rows.append([InlineKeyboardButton(text=BTN_CANCEL, callback_data=CB_ONBOARDING_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_confirm_kb():
    """Подтверждение создания события"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONFIRM), KeyboardButton(text=BTN_EDIT)],
            [KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_CANCEL)]
        ],
        resize_keyboard=True
    )

# === КЛАВИАТУРЫ ПОИСКА СОБЫТИЙ ===
def get_event_list_kb(events):
    """Список событий для поиска"""
    buttons = []
    for event in events:
        event_id, event_type, max_participants, date_time, confirmed_count = event
        # Показать имя события на первой строке, а город/статус на второй строке
        text = f"{event_type[:20]}\n{confirmed_count}/{max_participants} • {date_time}"
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"{CB_EVENT_VIEW}{event_id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_search_city_choice_kb(user_city: str = None):
    """Клавиатура выбора города при поиске событий"""
    buttons = []
    row = []
    # Мой город
    text_my = "📍 Мой город"
    buttons.append([InlineKeyboardButton(text=text_my, callback_data=CB_SEARCH_USE_MY_CITY)])
    # Выбрать другой город
    buttons.append([InlineKeyboardButton(text="🏙 Выбрать другой город", callback_data=CB_SEARCH_CHOOSE_CITY)])
    # Отмена/назад
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_premium_event_kb(event_id: int, current_index: int, total: int, user_telegram_id: int, is_confirmed: bool, city_key: str):
    """Inline keyboard for premium single-event card with navigation."""
    kb = []

    # Navigation row
    prev_cb = f"{CB_EVENT_NAV_PREV}{current_index}:{city_key}"
    next_cb = f"{CB_EVENT_NAV_NEXT}{current_index}:{city_key}"
    nav_row = []
    nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=prev_cb))
    nav_row.append(InlineKeyboardButton(text=f"{current_index+1}/{total}", callback_data=f"{CB_EVENT_SHOW}{event_id}"))
    nav_row.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=next_cb))
    kb.append(nav_row)

    # Action row
    if not is_confirmed:
        kb.append([InlineKeyboardButton(text="✅ Пойти", callback_data=f"{CB_EVENT_JOIN}{event_id}")])

    kb.append([InlineKeyboardButton(text="🔙 К списку городов", callback_data=CB_SEARCH_CHOOSE_CITY)])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_event_details_kb(event_id, user_telegram_id, is_confirmed=False):
    """Детали события"""
    buttons = []
    
    if not is_confirmed:
        buttons.append([InlineKeyboardButton(text="💳 Забронировать", callback_data=f"{CB_EVENT_JOIN}{event_id}")])
    
    buttons.append([
        InlineKeyboardButton(text="📲 Пригласить друга", callback_data=f"{CB_EVENT_INVITE}{event_id}:{user_telegram_id}")
    ])
    # Возврат к премиум-списку событий (использует FSM return_context)
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=CB_BACK_TO_EVENTS)])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_kb(event_id):
    """Оплата участия в событии"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 99 ₽", url="https://yoomoney.ru/pay/...")],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"{CB_EVENT_PAID}{event_id}")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data=f"{CB_EVENT_BACK}{event_id}")]
        ]
    )

# === КЛАВИАТУРЫ ПРОФИЛЯ ===
def get_profile_kb(telegram_id, admin_ids, is_creator=False):
    """Меню профиля"""
    keyboard = []
    
    # Кнопка админки ТОЛЬКО для админов
    if telegram_id in admin_ids:
        keyboard.append([InlineKeyboardButton(text=BTN_ADMIN, callback_data="admin:menu")])
    
    # Основные кнопки профиля
    keyboard.append([InlineKeyboardButton(text=BTN_MY_BOOKINGS, callback_data=CB_PROFILE_MY_BOOKINGS)])
    keyboard.append([InlineKeyboardButton(text=BTN_MY_EVENTS, callback_data=CB_PROFILE_MY_EVENTS)])
    # Кнопка запроса вывода (показывается динамически из кода, но оставить возможность добавить)
    keyboard.append([InlineKeyboardButton(text="💸 Запрос вывода", callback_data="withdraw:request")])
    keyboard.append([InlineKeyboardButton(text=BTN_BACK + " в главное меню", callback_data=CB_NAV_BACK_TO_MAIN)])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_my_events_kb(events):
    """Список моих событий"""
    buttons = []
    for event in events:
        event_id, event_type, city, date_time, status, participants_count, max_participants = event
        status_emoji = "✅" if status == 'ACTIVE' else "❌"
        # Две строки: заголовок и вспомогательная информация
        text = f"{status_emoji} {event_type[:20]}\n{city} • {participants_count}/{max_participants}"

        # Основная кнопка — переход к деталям события (существующий callback не меняем)
        row = [
            InlineKeyboardButton(
                text=text,
                callback_data=f"{CB_EVENT_MY}{event_id}"
            )
        ]

        # Если событие активно и это список создаваемых пользователем событий,
        # показываем дополнительную кнопку для отмены события.
        if status == 'ACTIVE':
            row.append(
                InlineKeyboardButton(
                    text="❌ Отменить событие",
                    callback_data=f"cancel_event:{event_id}"
                )
            )

        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_PROFILE)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_my_bookings_kb(bookings):
    """Список моих бронирований"""
    buttons = []
    for booking in bookings:
        event_id, event_type, city, date_time, booking_date = booking
        
        booking_dt = datetime.fromisoformat(booking_date.replace(' ', 'T'))
        formatted_date = booking_dt.strftime("%d.%m.%Y")
        
        text = f"✅ {event_type[:20]}\n{city} • {date_time[:10]}"
        
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"{CB_EVENT_VIEW}{event_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"{CB_BOOKING_CANCEL}{event_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_PROFILE)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_event_manage_kb(event_id):
    """Управление моим событием"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список участников", callback_data=f"{CB_EVENT_PARTICIPANTS}{event_id}")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data=CB_NAV_BACK_TO_MY_EVENTS)]
        ]
    )

def get_participants_kb(event_id, participants):
    """Список участников события"""
    buttons = []
    for participant in participants:
        username, telegram_id, name, joined_at = participant
        display_name = f"@{username}" if username else name or f"ID: {telegram_id}"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {display_name[:25]}",
                callback_data=f"{CB_USER_INFO}{telegram_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=BTN_BACK, callback_data=f"{CB_EVENT_MY}{event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
