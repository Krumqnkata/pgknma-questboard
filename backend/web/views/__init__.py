"""Страниците за ученици и учители (Django шаблони), разделени по теми."""
from .game import (  # noqa: F401
    home, leaderboard_view, profile, purchase_list, purchase_use, review_claim, review_list, shop, shop_buy,
)
from .missions import mission_create, mission_detail, mission_edit, mission_list  # noqa: F401
