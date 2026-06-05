import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import Platform
from app.db.models import Search
from app.keyboards.menu import BTN_ADD_SEARCH, BTN_MY_SEARCHES, MENU_BUTTONS, main_menu_keyboard
from app.keyboards.search import (
    NO_LIMIT,
    CancelAddCallback,
    PriceMaxCallback,
    PriceMinCallback,
    cancel_add_keyboard,
    price_max_keyboard,
    price_min_keyboard,
)
from app.services.search_service import format_price_range, normalize_price
from app.services.subscription_service import refresh_premium_status
from app.services.user_service import get_or_create_user_in_session

router = Router()
logger = logging.getLogger(__name__)

FREE_SEARCH_LIMIT = 2


class AddSearchFSM(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_custom_price_min = State()
    waiting_for_custom_price_max = State()


class DeleteSearchCallback(CallbackData, prefix="del_search"):
    search_id: str


def build_searches_keyboard(searches: list[Search]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for search in searches:
        price_text = format_price_range(search.price_min, search.price_max)
        builder.button(
            text=f"🗑 {search.keyword} ({price_text})",
            callback_data=DeleteSearchCallback(search_id=str(search.id)),
        )
    builder.adjust(1)
    return builder.as_markup()


async def _check_search_limit(message: Message, session: AsyncSession) -> bool:
    """Return True if user can add another search."""
    if message.from_user is None:
        return False

    user = await get_or_create_user_in_session(session, message.from_user)
    await refresh_premium_status(session, user)

    if user.is_premium:
        return True

    active_count = await session.scalar(
        select(func.count(Search.id)).where(
            Search.user_id == user.id,
            Search.is_active.is_(True),
        )
    )
    if (active_count or 0) >= FREE_SEARCH_LIMIT:
        await message.answer(
            "⚠️ <b>Free limit reached</b> (max 2 active searches).\n\n"
            "Remove a search via <b>📋 My Searches</b> or upgrade with <b>⭐ Go Premium</b>.",
            reply_markup=main_menu_keyboard(),
        )
        return False
    return True


async def _start_add_flow(message: Message, state: FSMContext) -> None:
    await message.answer(
        "🔎 <b>New search</b> (Mercari)\n\n"
        "Type a keyword to watch for — e.g. <code>Pokemon</code> or <code>Nike AF1</code>:",
        reply_markup=cancel_add_keyboard(),
    )
    await state.set_state(AddSearchFSM.waiting_for_keyword)


async def _save_search(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    *,
    price_min: int | None,
    price_max: int | None,
) -> None:
    if message.from_user is None:
        await state.clear()
        return

    data = await state.get_data()
    keyword: str = data["keyword"]

    if price_max is not None and price_min is not None and price_min > price_max:
        await message.answer(
            "Minimum price cannot exceed maximum. Start over with <b>➕ Add Search</b>.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    user = await get_or_create_user_in_session(session, message.from_user)

    existing = await session.scalar(
        select(Search).where(
            Search.user_id == user.id,
            Search.platform == Platform.MERCARI,
            Search.keyword == keyword,
            Search.price_min == price_min,
            Search.price_max == price_max,
        )
    )

    if existing is not None:
        if existing.is_active:
            await message.answer(
                "⚠️ This search already exists. Check <b>📋 My Searches</b>.",
                reply_markup=main_menu_keyboard(),
            )
            await state.clear()
            return
        existing.is_active = True
        action = "restored"
    else:
        session.add(
            Search(
                user_id=user.id,
                platform=Platform.MERCARI,
                keyword=keyword,
                price_min=price_min,
                price_max=price_max,
            )
        )
        action = "created"

    await state.clear()
    price_text = format_price_range(price_min, price_max)
    await message.answer(
        f"✅ Search {action}!\n\n"
        f"🔎 <b>{keyword}</b>\n"
        f"💰 {price_text}\n"
        f"📡 You'll get alerts when new items appear.",
        reply_markup=main_menu_keyboard(),
    )
    logger.info("User %s %s search %r", user.telegram_id, action, keyword)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Nothing to cancel.", reply_markup=main_menu_keyboard())
        return
    await state.clear()
    await message.answer("Search setup cancelled.", reply_markup=main_menu_keyboard())


@router.callback_query(CancelAddCallback.filter())
async def cancel_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.edit_text("Search setup cancelled.")
        await callback.message.answer("Main menu:", reply_markup=main_menu_keyboard())


@router.message(Command("add"))
@router.message(F.text == BTN_ADD_SEARCH)
async def cmd_add_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _check_search_limit(message, session):
        return
    await _start_add_flow(message, state)


@router.message(AddSearchFSM.waiting_for_keyword, F.text, ~F.text.in_(MENU_BUTTONS))
async def process_keyword(message: Message, state: FSMContext) -> None:
    keyword = message.text.strip() if message.text else ""
    if not keyword:
        await message.answer("Keyword cannot be empty. Try again:")
        return

    await state.update_data(keyword=keyword)
    await message.answer(
        f"Keyword: <b>{keyword}</b>\n\n"
        "Select a <b>minimum price</b>:",
        reply_markup=price_min_keyboard(),
    )


@router.callback_query(PriceMinCallback.filter())
async def process_price_min_callback(
    callback: CallbackQuery,
    callback_data: PriceMinCallback,
    state: FSMContext,
) -> None:
    if callback_data.value == 0:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Enter <b>minimum price</b> in JPY (send <code>0</code> for no minimum):"
            )
        await state.set_state(AddSearchFSM.waiting_for_custom_price_min)
        return

    price_min = None if callback_data.value == NO_LIMIT else callback_data.value
    await state.update_data(price_min=price_min)
    await callback.answer()

    if callback.message:
        label = "No minimum" if price_min is None else f"¥{price_min:,}"
        await callback.message.edit_text(
            f"Minimum: <b>{label}</b>\n\nSelect a <b>maximum price</b>:",
            reply_markup=price_max_keyboard(),
        )


@router.message(AddSearchFSM.waiting_for_custom_price_min, F.text)
async def process_custom_price_min(message: Message, state: FSMContext) -> None:
    try:
        raw = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Please enter a number (e.g. <code>1000</code>) or <code>0</code>.")
        return
    if raw < 0:
        await message.answer("Price cannot be negative.")
        return

    price_min = normalize_price(raw)
    await state.update_data(price_min=price_min)
    label = "No minimum" if price_min is None else f"¥{price_min:,}"
    await message.answer(
        f"Minimum: <b>{label}</b>\n\nSelect a <b>maximum price</b>:",
        reply_markup=price_max_keyboard(),
    )


@router.callback_query(PriceMaxCallback.filter())
async def process_price_max_callback(
    callback: CallbackQuery,
    callback_data: PriceMaxCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback_data.value == 0:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Enter <b>maximum price</b> in JPY (send <code>0</code> for no maximum):"
            )
        await state.set_state(AddSearchFSM.waiting_for_custom_price_max)
        return

    price_max = None if callback_data.value == NO_LIMIT else callback_data.value
    await callback.answer()

    data = await state.get_data()
    price_min = data.get("price_min")

    if callback.message:
        await _save_search(
            callback.message,
            session,
            state,
            price_min=price_min,
            price_max=price_max,
        )


@router.message(AddSearchFSM.waiting_for_custom_price_max, F.text)
async def process_custom_price_max(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    try:
        raw = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.answer("Please enter a number or <code>0</code>.")
        return
    if raw < 0:
        await message.answer("Price cannot be negative.")
        return

    data = await state.get_data()
    price_min = data.get("price_min")
    price_max = normalize_price(raw)
    await _save_search(message, session, state, price_min=price_min, price_max=price_max)


@router.message(Command("list"))
@router.message(F.text == BTN_MY_SEARCHES)
async def cmd_list_searches(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user = await get_or_create_user_in_session(session, message.from_user)
    await refresh_premium_status(session, user)

    result = await session.execute(
        select(Search)
        .where(Search.user_id == user.id, Search.is_active.is_(True))
        .order_by(Search.created_at.desc())
    )
    searches = result.scalars().all()

    plan = "Premium ⭐" if user.is_premium else f"Free ({len(searches)}/{FREE_SEARCH_LIMIT})"

    if not searches:
        await message.answer(
            f"📋 <b>My Searches</b> — {plan}\n\n"
            "No active searches yet.\nTap <b>➕ Add Search</b> to create one.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"📋 <b>My Searches</b> — {plan}\n\n"
        "Tap a search below to remove it:",
        reply_markup=build_searches_keyboard(searches),
    )


@router.callback_query(DeleteSearchCallback.filter())
async def process_delete_search(
    callback: CallbackQuery,
    callback_data: DeleteSearchCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    try:
        search_uuid = uuid.UUID(callback_data.search_id)
    except ValueError:
        await callback.answer("Invalid search ID.", show_alert=True)
        return

    user = await get_or_create_user_in_session(session, callback.from_user)

    search = await session.scalar(
        select(Search).where(
            Search.id == search_uuid,
            Search.user_id == user.id,
            Search.is_active.is_(True),
        )
    )

    if search is None:
        await callback.answer("Already removed.", show_alert=True)
        if callback.message:
            await callback.message.delete()
        return

    search.is_active = False
    logger.info("User %s deleted search %s", user.telegram_id, search_uuid)

    await callback.answer(f"Removed '{search.keyword}'")
    if callback.message:
        await callback.message.delete()
        await callback.message.answer(
            f"🛑 Search <b>{search.keyword}</b> stopped.",
            reply_markup=main_menu_keyboard(),
        )
