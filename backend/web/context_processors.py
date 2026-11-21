"""Данни, нужни на всяка страница (напр. броят чакащи заявки в менюто на учителя)."""
from missions.models import Claim


def navigation(request):
    user = request.user
    if user.is_authenticated and user.is_teacher:
        count = Claim.objects.filter(mission__created_by=user, status=Claim.Status.PENDING).count()
        return {"pending_review_count": count}
    return {}
