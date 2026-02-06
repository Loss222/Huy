# states.py
"""
Все группы состояний бота
"""
from aiogram.fsm.state import State, StatesGroup

# === СОСТОЯНИЯ ОСНОВНОГО ПОТОКА ===
class MainStates(StatesGroup):
    MAIN_MENU = State()
    VIEWING_EVENT = State()

# === СОСТОЯНИЯ СОЗДАНИЯ СОБЫТИЯ ===
class CreateEventStates(StatesGroup):
    step_1 = State()
    TYPE = State()
    TYPE_OTHER = State()
    DATE = State()
    TIME = State()
    MAX_PARTICIPANTS = State()
    DESCRIPTION = State()
    CONTACT = State()
    CONFIRMATION = State()
    FORMAT = State()
    TYPE_SELECT = State()

# === СОСТОЯНИЯ ПОИСКА СОБЫТИЙ ===
class SearchEventsStates(StatesGroup):
    SELECT_EVENT = State()
    CHOOSE_CITY = State()

# === СОСТОЯНИЯ ПРИСОЕДИНЕНИЯ К СОБЫТИЮ ===
class JoinEventStates(StatesGroup):
    PAYMENT_INFO = State()

# === СОСТОЯНИЯ ПРОФИЛЯ ===
class ProfileStates(StatesGroup):
    VIEWING = State()
    MY_EVENTS = State()
    MY_BOOKINGS = State()

# === СОСТОЯНИЯ ОНБОРДИНГА ===
class OnboardingStates(StatesGroup):
    NAME = State()
    CITY = State()