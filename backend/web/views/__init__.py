"""Страниците за ученици и учители (Django шаблони), разделени по теми."""
from .game import (  # noqa: F401
    claim_undo, home, leaderboard_view, profile, purchase_list, purchase_use, review_claim, review_list, shop, shop_buy,
)
from .missions import mission_create, mission_detail, mission_edit, mission_list  # noqa: F401
from .assistant import assistant_chat, mission_hint  # noqa: F401
from .reports import reports  # noqa: F401
from .branding import school_logo  # noqa: F401
from .password import QuestboardPasswordChangeView  # noqa: F401
from .notifications import notifications  # noqa: F401
from .pages import privacy, terms  # noqa: F401
from .app import favicon, manifest, offline, service_worker  # noqa: F401
from .evidence import evidence_file  # noqa: F401
from .rewards import rewards  # noqa: F401
