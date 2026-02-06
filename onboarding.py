# onboarding.py
"""
Модуль онбординга бота VIBEZ
"""
import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

from texts import *
from keyboards import get_cities_keyboard, get_main_menu_kb
from cities import CITIES
from database import Database
from states import OnboardingStates, MainStates
CB_CITY_SELECT = "city:select:"
CB_CITY_PAGE = "city:page:"
CB_ONBOARDING_CANCEL = "onboarding:cancel"

def register_onboarding(db: Database, admin_ids: list):
    """Регистрация онбординг-роутера"""
    logging.info("register_onboarding called")
    onboarding_router = Router()
    
    @onboarding_router.message(StateFilter(OnboardingStates.NAME))
    async def process_name(message: Message, state: FSMContext):
        if message.text == BTN_CANCEL:
            await state.clear()
            await state.set_state("MainStates:MAIN_MENU")
            await message.answer(ONBOARDING_CANCELLED, reply_markup=get_main_menu_kb(message.from_user.id, admin_ids))
            return
        
        name = message.text.strip()
        if len(name) < 2:
            await message.answer(ERROR_NAME_TOO_SHORT)
            return
        
        await state.update_data(name=name)
        await state.set_state(OnboardingStates.CITY)
        
        await message.answer(
            ONBOARDING_CITY_SELECTION.format(name=name),
            reply_markup=get_cities_keyboard()
        )
    
    @onboarding_router.callback_query(F.data.startswith(CB_CITY_PAGE), StateFilter(OnboardingStates.CITY))
    async def process_city_page(callback: CallbackQuery, state: FSMContext):
        """Обработчик пагинации списка городов"""
        # защита: логируем и отвечаем на callback в любом случае
        try:
            logging.info(f"process_city_page called: data={callback.data}, from={callback.from_user.id}")
            page = int(callback.data.split(CB_CITY_PAGE, 1)[1])
            await callback.message.edit_reply_markup(
                reply_markup=get_cities_keyboard(page)
            )
        except Exception as e:
            logging.exception(f"Error in city pagination: {e}")
        finally:
            try:
                await callback.answer()
            except Exception:
                pass
    
    @onboarding_router.callback_query(F.data.startswith(CB_CITY_SELECT), StateFilter(OnboardingStates.CITY))
    async def process_city_selection(callback: CallbackQuery, state: FSMContext):
        logging.info(f"process_city_selection called: data={callback.data}, from={callback.from_user.id}")
        try:
            idx_str = callback.data.split(CB_CITY_SELECT, 1)[1]
            city_idx = int(idx_str)
            city = CITIES[city_idx]
        except Exception:
            await callback.answer()
            return
        data = await state.get_data()
        name = data.get('name')
        if not name:
            # Некорректные данные сессии — спросим имя заново
            await state.clear()
            await state.set_state(OnboardingStates.NAME)
            await callback.message.answer(WELCOME_ONBOARDING, reply_markup=ReplyKeyboardRemove())
            await callback.answer()
            return
        
        await db.update_user_profile(callback.from_user.id, name, city)
        
        invite_event_id = data.get('invite_event_id')
        
        if invite_event_id:
            await state.set_state(MainStates.VIEWING_EVENT)
            await state.update_data(current_event_id=invite_event_id)
            
            event = await db.get_event_details(invite_event_id)
            if event:
                (event_type, custom_type, event_city, date, time, max_participants, 
                 description, contact, status, creator_id, creator_username, 
                 creator_name, confirmed_count) = event
                
                display_type = custom_type or event_type
                
                is_confirmed = await db.is_user_confirmed(invite_event_id, callback.from_user.id)
                
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
                
                from keyboards import get_event_details_kb
                await callback.message.edit_text(text)
                await callback.message.answer(
                    text, 
                    reply_markup=get_event_details_kb(invite_event_id, callback.from_user.id, is_confirmed)
                )
            else:
                await callback.message.edit_text(
                    ONBOARDING_COMPLETE.format(name=name, city=city)
                )
                await state.set_state("MainStates:MAIN_MENU")
                await callback.message.answer(
                    BACK_TO_MAIN,
                    reply_markup=get_main_menu_kb(callback.from_user.id, admin_ids)
                )
        else:
            await state.set_state(MainStates.MAIN_MENU)
            await callback.message.edit_text(
                ONBOARDING_COMPLETE.format(name=name, city=city)
            )
            await callback.message.answer(
                BACK_TO_MAIN,
                reply_markup=get_main_menu_kb(callback.from_user.id, admin_ids)
            )
        try:
            await callback.answer()
        except Exception:
            pass
    
    @onboarding_router.callback_query(F.data == CB_ONBOARDING_CANCEL)
    async def cancel_onboarding(callback: CallbackQuery, state: FSMContext):
        """Отмена онбординга"""
        current_state = await state.get_state()
        if current_state not in [OnboardingStates.NAME.state, OnboardingStates.CITY.state]:
            return
        
        await state.clear()
        await state.set_state(MainStates.MAIN_MENU)
        await callback.message.edit_text(ONBOARDING_CANCELLED)
        await callback.message.answer(
            BACK_TO_MAIN,
            reply_markup=get_main_menu_kb(callback.from_user.id, admin_ids)
        )
        await callback.answer()
    
    # Включаем онбординг-роутер в основной
    # router.include_router(onboarding_router)
    return onboarding_router
