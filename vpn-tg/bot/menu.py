from __future__ import annotations

from typing import Tuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .utils import BotConfig


class MenuRenderer:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def root(self) -> Tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔑 Получить/показать ключ", callback_data="menu:keys")
        builder.button(text="❓ Помощь", callback_data="menu:help")
        builder.button(text="🌍 Расширение для браузера", callback_data="menu:browser")
        builder.button(text="💖 Донат на развитие", callback_data="menu:donate")
        builder.adjust(1)
        text = "Выберите действие ⬇️"
        return text, builder.as_markup()

    def keys(self) -> Tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        builder.button(text="Получить ключ", callback_data="keys:get")
        builder.button(text="🧾 QR-код", callback_data="keys:qr")
        builder.button(text="♻️ Пересоздать ключ", callback_data="keys:recreate")
        builder.button(text="⬅️ Назад", callback_data="menu:root")
        builder.adjust(1)
        text = "🔑 Управление ключом"
        return text, builder.as_markup()

    def help_root(self) -> Tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        builder.button(text="📱 Android", callback_data="help:android")
        builder.button(text="🍏 iOS", callback_data="help:ios")
        builder.button(text="🖥 Windows", callback_data="help:windows")
        builder.button(text="❓ Общие советы", callback_data="help:faq")
        builder.button(text="⬅️ Назад", callback_data="menu:root")
        builder.adjust(1)
        text = "❓ Помощь"
        return text, builder.as_markup()

    def browser(self) -> Tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔗 Ссылка на скачивание", callback_data="browser:link")
        builder.button(text="📘 Инструкция", callback_data="browser:guide")
        builder.button(text="⬅️ Назад", callback_data="menu:root")
        builder.adjust(1)
        text = "🌍 Расширение для браузера"
        return text, builder.as_markup()

    def donate(self) -> Tuple[str, InlineKeyboardMarkup]:
        builder = InlineKeyboardBuilder()
        donate_url = self.config.links.get("donate_url")
        if donate_url:
            builder.button(text="💖 Поддержать проект", url=donate_url)
        builder.button(text="⬅️ Назад", callback_data="menu:root")
        builder.adjust(1)
        text = "💖 Поддержите проект"
        return text, builder.as_markup()
