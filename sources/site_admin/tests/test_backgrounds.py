from pathlib import Path
from unittest.mock import patch

from nfc_cards.services import backgrounds

_MINI_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500001a0d21bc"
)


def test_thumb_fallback_equals_full_when_no_thumb_file(tmp_path):
    bg = tmp_path / "static" / "hexgraph" / "backgrounds"
    bg.mkdir(parents=True)
    (bg / "only_full.png").write_bytes(_MINI_PNG)

    with patch.object(backgrounds, "_bg_dir", return_value=bg):
        lst = backgrounds.list_background_images()
    assert len(lst) == 1
    assert lst[0]["full"] == "hexgraph/backgrounds/only_full.png"
    assert lst[0]["thumb"] == lst[0]["full"]


def test_thumb_when_file_in_thumbs_dir(tmp_path):
    bg = tmp_path / "static" / "hexgraph" / "backgrounds"
    (bg / "thumbs").mkdir(parents=True)
    (bg / "x.png").write_bytes(_MINI_PNG)
    (bg / "thumbs" / "x.webp").write_bytes(b"x")

    with patch.object(backgrounds, "_bg_dir", return_value=bg):
        lst = backgrounds.list_background_images()
    assert len(lst) == 1
    assert lst[0]["full"] == "hexgraph/backgrounds/x.png"
    assert lst[0]["thumb"] == "hexgraph/backgrounds/thumbs/x.webp"


def test_nested_romantic_style_paths(tmp_path):
    bg = tmp_path / "static" / "hexgraph" / "backgrounds"
    romantic = bg / "romantic"
    thumbs = romantic / "thumbs"
    thumbs.mkdir(parents=True)
    (romantic / "hearts.png").write_bytes(_MINI_PNG)
    (thumbs / "hearts.webp").write_bytes(b"w")

    with patch.object(backgrounds, "_bg_dir", return_value=bg):
        lst = backgrounds.list_background_images()
    assert len(lst) == 1
    assert lst[0]["full"] == "hexgraph/backgrounds/romantic/hearts.png"
    assert lst[0]["thumb"] == "hexgraph/backgrounds/romantic/thumbs/hearts.webp"
