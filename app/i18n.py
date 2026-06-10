from typing import Literal

from fastapi import Request


Language = Literal["ru", "en"]
DEFAULT_LANGUAGE: Language = "ru"

MESSAGES: dict[str, dict[Language, str]] = {
    "api_key.invalid_or_missing": {
        "ru": "Некорректный или отсутствующий API ключ.",
        "en": "Invalid or missing API key.",
    },
    "object.not_found": {
        "ru": "Объект не найден.",
        "en": "Object not found.",
    },
    "object.invalid_access_key": {
        "ru": "Некорректный ключ доступа для этого объекта.",
        "en": "Invalid access key for this object.",
    },
    "image.invalid_type": {
        "ru": "Загруженный файл должен быть изображением.",
        "en": "Uploaded file must be an image.",
    },
    "date.invalid_format": {
        "ru": "Дата должна быть в формате YYYY-MM-DD или YYYY-MM-DD - YYYY-MM-DD.",
        "en": "date must be YYYY-MM-DD or YYYY-MM-DD - YYYY-MM-DD.",
    },
    "date.invalid_period_order": {
        "ru": "start_date должен быть раньше end_date или равен ему.",
        "en": "start_date must be earlier than or equal to end_date.",
    },
    "date.period_required": {
        "ru": "Для периода нужно передать start_date и end_date.",
        "en": "Both start_date and end_date are required for a period.",
    },
    "date.single_or_period": {
        "ru": "Передайте либо date, либо период start_date/end_date.",
        "en": "Send either date or start_date/end_date period.",
    },
    "date.already_booked": {
        "ru": "Одна или несколько дат уже забронированы для этого объекта.",
        "en": "One or more dates are already booked for this object.",
    },
    "booked_date.not_found": {
        "ru": "Забронированная дата не найдена.",
        "en": "Booked date not found.",
    },
    "booked_dates.not_found": {
        "ru": "Забронированные даты в указанном диапазоне не найдены.",
        "en": "Booked dates in the specified range were not found.",
    },
}

MESSAGE_KEYS_BY_ENGLISH = {
    translations["en"]: key for key, translations in MESSAGES.items()
}


def get_language(request: Request) -> Language:
    header_values = (
        request.headers.get("x-language", ""),
        request.headers.get("accept-language", ""),
    )
    for header_value in header_values:
        language = language_from_header(header_value)
        if language is not None:
            return language
    return DEFAULT_LANGUAGE


def language_from_header(header_value: str) -> Language | None:
    for item in header_value.split(","):
        language = item.split(";")[0].strip().lower()
        if not language:
            continue
        short_language = language.split("-")[0]
        if short_language == "ru":
            return "ru"
        if short_language == "en":
            return "en"
    return None


def t(message_key: str, language: Language) -> str:
    return MESSAGES[message_key][language]


def translate_detail(detail: str, language: Language) -> str:
    message_key = MESSAGE_KEYS_BY_ENGLISH.get(detail)
    if message_key is None:
        return detail
    return t(message_key, language)
