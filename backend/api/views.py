"""
REST API на Questboard. Отговорите са в JSON.

Всички адреси изискват вход, освен /api/health/.
Правата се проверяват тук по ролята, а правилата на играта са в missions/services.py.
"""
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStudent, IsTeacher
from missions.models import Claim, Mission
from missions.services import GameRuleError, missions_for_student, missions_for_teacher, submit_claim

from .serializers import ClaimCreateSerializer, ClaimSerializer, MeSerializer, MissionSerializer


class HealthView(APIView):
    """Проверка, че основното API работи."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    """Кой е влезлият потребител и каква е ролята му."""

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class MissionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Мисии.
      - ученик: вижда активните мисии и заявява изпълнение (POST /api/missions/<id>/claim/);
      - учител: вижда, създава и редактира своите мисии.
    Мисии не се трият – само се спират (is_active=false).
    """

    serializer_class = MissionSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_teacher:
            return missions_for_teacher(user)
        if user.is_student:
            return missions_for_student()
        return Mission.objects.select_related("guild")  # администратор

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsStudent],
            serializer_class=ClaimCreateSerializer)
    def claim(self, request, pk=None):
        """Ученикът заявява изпълнение. Срокът се проверява в submit_claim."""
        mission = get_object_or_404(Mission, pk=pk, is_active=True)
        data = ClaimCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claim = submit_claim(request.user, mission, data.validated_data["evidence"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class ClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Заявки (само за четене засега).
      - ученик: своите заявки;
      - учител: заявките по своите мисии.
    """

    serializer_class = ClaimSerializer

    def get_queryset(self):
        user = self.request.user
        claims = Claim.objects.select_related("mission", "student")
        if user.is_student:
            return claims.filter(student=user)
        if user.is_teacher:
            return claims.filter(mission__created_by=user)
        return claims  # администратор
