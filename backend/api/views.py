"""
REST API на Questboard. Отговорите са в JSON.

Всички адреси изискват вход, освен /api/health/.
"""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import MeSerializer


class HealthView(APIView):
    """Проверка, че основното API работи."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    """Кой е влезлият потребител и каква е ролята му."""

    def get(self, request):
        return Response(MeSerializer(request.user).data)
