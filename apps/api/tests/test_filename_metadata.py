from __future__ import annotations

from retroweb.library.metadata import FilenameMetadataProvider
from retroweb.library.systems import GameSystem


def parse(name: str):  # type: ignore[no-untyped-def]
    return FilenameMetadataProvider().from_filename(name, GameSystem.PSP)


def test_catalogue_number_before_a_cjk_title_is_dropped() -> None:
    meta = parse("2851 - 12点的钟声与灰姑娘-万圣节婚礼 [简] [心游汉化组].iso")
    assert meta is not None
    assert meta.title == "12点的钟声与灰姑娘-万圣节婚礼"
    assert meta.label == "简, 心游汉化组"
    assert meta.region is None


def test_no_intro_numbers_stay_in_the_title() -> None:
    assert parse("007 - NightFire (USA, Europe) (En,Fr,De).gba").title == "007 - NightFire"  # type: ignore[union-attr]
    assert parse("1080 Snowboarding (USA).z64").title == "1080 Snowboarding"  # type: ignore[union-attr]
    assert parse("2851 - Some English Game (USA).iso").title == "2851 - Some English Game"  # type: ignore[union-attr]


def test_numeric_cjk_title_without_index_is_kept() -> None:
    meta = parse("428 被封锁的浩谷 V1.1 [简].iso")
    assert meta is not None
    assert meta.title == "428 被封锁的浩谷 V1.1"
