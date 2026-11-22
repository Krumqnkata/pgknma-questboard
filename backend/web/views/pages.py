"""Условията за ползване и политиката за поверителност – отворени за всички, без вход."""
from django.shortcuts import get_object_or_404, render

from ..models import SitePage


def site_page(request, slug):
    page = get_object_or_404(SitePage, slug=slug)
    return render(request, "web/site_page.html", {"site_page": page})


def terms(request):
    return site_page(request, SitePage.Slug.TERMS)


def privacy(request):
    return site_page(request, SitePage.Slug.PRIVACY)
