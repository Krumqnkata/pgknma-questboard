"""
Сайтът като приложение на телефона (PWA): описание на приложението (manifest),
service worker и страница „Няма връзка“.

Service worker-ът НЕ пази страниците с данни – само показва „Няма връзка“,
ако интернетът липсва. Така никой не вижда стари или чужди данни.
"""
from django.http import HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

from economy.models import GameSettings

SERVICE_WORKER = """// Questboard – service worker (web/views/app.py)
const CACHE = "questboard-offline-v1";
const OFFLINE = "/offline/";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(new Request(OFFLINE, { cache: "reload" }))));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))));
  self.clients.claim();
});

// Само при отваряне на страница: първо от сървъра, а без интернет – „Няма връзка“.
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});
"""


@cache_control(max_age=3600)
def manifest(request):
    school = GameSettings.load().school_name
    return JsonResponse({
        "name": f"Questboard – {school}" if school else "Questboard",
        "short_name": "Questboard",
        "description": "Мисии, точки и награди в училищния живот.",
        "lang": "bg",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f7f7f5",
        "theme_color": "#14151a",
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("icons/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }, content_type="application/manifest+json", json_dumps_params={"ensure_ascii": False})


@cache_control(no_cache=True)
def service_worker(request):
    return HttpResponse(SERVICE_WORKER, content_type="application/javascript")


def offline(request):
    return render(request, "web/offline.html")


def favicon(request):
    """
    Браузърите търсят /favicon.ico сами – и на страници без <link rel="icon">
    (администрацията, API-то, файлове). Пращаме ги към иконата в static/.
    """
    return HttpResponsePermanentRedirect(static("icons/favicon.ico"))
