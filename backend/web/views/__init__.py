"""Страниците за ученици и учители (Django шаблони), разделени по теми."""
from .game import (  # noqa: F401
    claim_undo, home, leaderboard_view, profile, purchase_list, purchase_use, review_claim, review_list, shop, shop_buy,
)
from .missions import homework_create, mission_create, mission_detail, mission_edit, mission_list, team_leave  # noqa: F401
from .assistant import assistant_chat, mission_hint  # noqa: F401
from .reports import reports  # noqa: F401
from .branding import school_logo, sponsor_logo  # noqa: F401
from .password import QuestboardPasswordChangeView  # noqa: F401
from .notifications import notifications  # noqa: F401
from .pages import privacy, terms  # noqa: F401
from .app import favicon, manifest, offline, service_worker  # noqa: F401
from .evidence import evidence_file, mission_file  # noqa: F401
from .rewards import rewards  # noqa: F401
from .not_wordpress import not_wordpress  # noqa: F401
from .quizzes import (  # noqa: F401
    guild_list, session_open, test_attempt, test_create, test_edit, test_left, test_list, test_session, test_start,
)
