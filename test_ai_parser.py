"""Test script for AI-based event parsing."""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.ingestors.ai_parser_base import parse_event_with_ai


async def test_basic_event():
    """Test parsing a simple event."""
    print("=" * 60)
    print("TEST 1: Simple concert event")
    print("=" * 60)

    text = """
    🎵 Концерт группы "Крым-Рок"

    📅 15 декабря 2025 в 19:00
    📍 ДК "Севастополь", ул. Ленина 10
    💰 Билеты: 500-1000₽

    Приходите на грандиозное выступление легендарной группы!
    Забронировать билеты: +7 (978) 123-45-67
    """

    result = await parse_event_with_ai(
        text=text,
        source_url="https://example.com/concert/123",
        source_type="test",
        city="Севастополь",
        use_cache=False,
    )

    if result:
        print("✅ Event parsed successfully!")
        print(f"Title: {result['title']}")
        print(f"Date: {result['date']}")
        print(f"Time: {result['time']}")
        print(f"Venue: {result['venue_name']}")
        print(f"Price: {result['price_min']}-{result['price_max']} ₽")
        print(f"Category: {result['category']}")
        print(f"Phone: {result.get('phone')}")
    else:
        print("❌ Failed to parse event")

    return result is not None


async def test_not_event():
    """Test that non-events are rejected."""
    print("\n" + "=" * 60)
    print("TEST 2: Non-event text (should be rejected)")
    print("=" * 60)

    text = """
    Всем привет! Сегодня отличная погода в Севастополе.
    Пойду гулять по набережной. Кто со мной?
    """

    result = await parse_event_with_ai(
        text=text,
        source_url=None,
        source_type="test",
        city="Севастополь",
        use_cache=False,
    )

    if result is None:
        print("✅ Correctly rejected non-event")
        return True
    else:
        print("❌ Incorrectly classified as event")
        return False


async def test_complex_event():
    """Test parsing event with multiple fields."""
    print("\n" + "=" * 60)
    print("TEST 3: Complex event with multiple details")
    print("=" * 60)

    text = """
    Выставка современного искусства "Крымские мотивы"

    Дата: 20-25 октября 2025
    Время работы: 10:00 - 18:00
    Место: Галерея "Арт-Пространство", Севастополь, пр. Нахимова 7
    Вход: Бесплатный

    Представлены работы 15 художников полуострова.

    Контакты:
    📧 info@artspace-crimea.ru
    📱 +7 (978) 999-88-77
    🔗 vk.com/artspace_crimea
    """

    result = await parse_event_with_ai(
        text=text,
        source_url="https://artspace.ru/exhibition/123",
        source_type="test",
        city="Севастополь",
        use_cache=False,
    )

    if result:
        print("✅ Complex event parsed successfully!")
        print(f"Title: {result['title']}")
        print(f"Date: {result['date']}")
        print(f"Venue: {result['venue_name']}")
        print(f"Address: {result.get('address')}")
        print(f"Category: {result['category']}")
        print(f"Free: {result.get('is_free')}")
        print(f"Email: {result.get('email')}")
        print(f"Phone: {result.get('phone')}")
        print(f"VK: {result.get('vk')}")
    else:
        print("❌ Failed to parse complex event")

    return result is not None


async def test_cache():
    """Test that caching works."""
    print("\n" + "=" * 60)
    print("TEST 4: Cache functionality")
    print("=" * 60)

    text = "Тестовое событие для проверки кеша"

    print("First call (should hit AI)...")
    result1 = await parse_event_with_ai(
        text=text,
        source_url=None,
        source_type="test",
        city="Севастополь",
        use_cache=True,
    )

    print("Second call (should hit cache)...")
    result2 = await parse_event_with_ai(
        text=text,
        source_url=None,
        source_type="test",
        city="Севастополь",
        use_cache=True,
    )

    if result1 == result2:
        print("✅ Cache works correctly (same result)")
        return True
    else:
        print("⚠️ Cache may not be working (different results)")
        return False


async def main():
    """Run all tests."""
    print("\n🤖 AI PARSER TEST SUITE\n")

    try:
        results = await asyncio.gather(
            test_basic_event(),
            test_not_event(),
            test_complex_event(),
            test_cache(),
            return_exceptions=True,
        )

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in results if r is True)
        total = len(results)

        print(f"Passed: {passed}/{total}")

        if passed == total:
            print("✅ All tests passed!")
        else:
            print("⚠️ Some tests failed")
            for i, r in enumerate(results, 1):
                if isinstance(r, Exception):
                    print(f"Test {i} raised exception: {r}")

    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
