"""Extract contact information from event descriptions."""

from __future__ import annotations

import re
from typing import Optional


def extract_phone(text: str) -> Optional[str]:
    """Extract phone number from text.

    Args:
        text: Text to search for phone number

    Returns:
        First phone number found or None
    """
    if not text:
        return None

    # Patterns for Russian phone numbers
    patterns = [
        r'\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 (900) 123-45-67
        r'8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',    # 8 (900) 123-45-67
        r'\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',                  # 900-123-45-67
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            # Clean up the phone number
            phone = match.group(0)
            phone = re.sub(r'[\s\-\(\)]', '', phone)  # Remove spaces, dashes, parentheses

            # Normalize to +7 format
            if phone.startswith('8') and len(phone) == 11:
                phone = '+7' + phone[1:]
            elif phone.startswith('7') and len(phone) == 11:
                phone = '+' + phone
            elif len(phone) == 10:
                phone = '+7' + phone

            return phone

    return None


def extract_email(text: str) -> Optional[str]:
    """Extract email address from text.

    Args:
        text: Text to search for email

    Returns:
        First email found or None
    """
    if not text:
        return None

    # Standard email pattern
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, text)

    if match:
        return match.group(0).lower()

    return None


def extract_telegram(text: str) -> Optional[str]:
    """Extract Telegram username from text.

    Args:
        text: Text to search for Telegram username

    Returns:
        Telegram username (without @) or None
    """
    if not text:
        return None

    # Patterns for Telegram usernames
    patterns = [
        r'@([a-zA-Z0-9_]{5,32})',           # @username
        r't\.me/([a-zA-Z0-9_]{5,32})',      # t.me/username
        r'telegram\.me/([a-zA-Z0-9_]{5,32})',  # telegram.me/username
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            username = match.group(1)
            # Filter out common non-username words
            if username.lower() not in ['admin', 'contact', 'support', 'info']:
                return username

    return None


def extract_vk(text: str) -> Optional[str]:
    """Extract VK profile/group link from text.

    Args:
        text: Text to search for VK link

    Returns:
        VK link or None
    """
    if not text:
        return None

    # Patterns for VK links
    patterns = [
        r'vk\.com/([a-zA-Z0-9_.]{3,})',
        r'vkontakte\.ru/([a-zA-Z0-9_.]{3,})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"https://vk.com/{match.group(1)}"

    return None


def extract_instagram(text: str) -> Optional[str]:
    """Extract Instagram username from text.

    Args:
        text: Text to search for Instagram username

    Returns:
        Instagram username or None
    """
    if not text:
        return None

    # Patterns for Instagram
    patterns = [
        r'instagram\.com/([a-zA-Z0-9_.]{1,30})',
        r'@([a-zA-Z0-9_.]{1,30})',  # Generic @ mention (lower priority)
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            username = match.group(1)
            if username.lower() not in ['admin', 'contact', 'support', 'info']:
                return username

    return None


def extract_all_contacts(text: str) -> dict[str, Optional[str]]:
    """Extract all contact information from text.

    Args:
        text: Text to search for contacts

    Returns:
        Dict with phone, email, telegram, vk, instagram
    """
    return {
        "phone": extract_phone(text),
        "email": extract_email(text),
        "telegram": extract_telegram(text),
        "vk": extract_vk(text),
        "instagram": extract_instagram(text),
    }


def format_contacts_for_display(contacts: dict[str, Optional[str]]) -> str:
    """Format contacts dict into readable string.

    Args:
        contacts: Dict from extract_all_contacts()

    Returns:
        Formatted string with contacts
    """
    parts = []

    if contacts.get("phone"):
        parts.append(f"📞 {contacts['phone']}")
    if contacts.get("email"):
        parts.append(f"📧 {contacts['email']}")
    if contacts.get("telegram"):
        parts.append(f"📱 @{contacts['telegram']}")
    if contacts.get("vk"):
        parts.append(f"🔵 {contacts['vk']}")
    if contacts.get("instagram"):
        parts.append(f"📸 @{contacts['instagram']}")

    return "\n".join(parts) if parts else "Контакты не найдены"


if __name__ == "__main__":
    # Test
    test_text = """
    Концерт в ДК Корабел
    Билеты: 500₽
    Телефон: +7 (978) 123-45-67
    Email: info@concert.ru
    Telegram: @concert_crimea
    VK: vk.com/concert_event
    """

    contacts = extract_all_contacts(test_text)
    print("Extracted contacts:")
    print(format_contacts_for_display(contacts))
