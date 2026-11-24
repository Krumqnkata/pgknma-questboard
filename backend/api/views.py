"""
REST API на Questboard. Отговорите са в JSON.

Всички адреси изискват вход, освен /api/health/.
Правата се проверяват тук по ролята, а правилата на играта са в missions/services.py.
"""
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsStudent, IsTeacher
from assistant_bridge.services import AssistantError, ask, draft_mission, request_hint
from badges.models import Badge
from badges.services import badge_cards, give_badge
from economy import leaderboard
from economy.models import Purchase
from economy.services import (
    active_privileges, approve_claim, bonus_left_this_week, buy_privilege, give_bonus, mark_purchase_used,
    reject_claim, student_stats, unused_purchases,
)
from missions.models import Claim, Mission
from missions.services import GameRuleError, missions_for_student, missions_for_teacher, missions_reviewed_by, parse_nicknames, submit_claim
from notifications.services import mark_all_read, recent_for, unread_count
from timetable import queries

from .serializers import (
    AnswerSerializer, BadgeCardSerializer, BadgeGiftRequestSerializer, BonusRequestSerializer, ClaimCreateSerializer, ClaimSerializer, DraftSerializer, HintSerializer,
    IdeaSerializer, MeSerializer, MissionSerializer, NotificationSerializer, PrivilegeSerializer, PurchaseSerializer,
    QuestionSerializer, RankingRowSerializer, ReviewSerializer, StatsSerializer,
)


class HealthView(APIView):
    """Проверка, че основното API работи."""

    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    """Кой е влезлият потребител и каква е ролята му."""

    @extend_schema(responses=MeSerializer)
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
        if getattr(self, "swagger_fake_view", False):  # при генериране на документацията няма потребител
            return Mission.objects.none()
        user = self.request.user
        if user.is_teacher:
            return missions_reviewed_by(user) if self.action in ("list", "retrieve") else missions_for_teacher(user)
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
        data = ClaimCreateSerializer(data={"evidence": request.data.get("evidence", ""),
                                           "teammates": request.data.get("teammates", "")})
        data.is_valid(raise_exception=True)
        try:
            claim = submit_claim(request.user, mission, data.validated_data["evidence"], request.FILES.getlist("files"),
                                 parse_nicknames(data.validated_data["teammates"]))
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ClaimSerializer(claim).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=HintSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsStudent])
    def hint(self, request, pk=None):
        """Подсказка от асистента срещу един Hint Token (Ф10)."""
        mission = get_object_or_404(Mission, pk=pk, is_active=True)
        try:
            hint = request_hint(request.user, mission)
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except AssistantError as error:
            return Response({"detail": f"{error} Hint Token-ът не е похарчен."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(HintSerializer(hint).data, status=status.HTTP_201_CREATED)


class ClaimViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Заявки.
      - ученик: своите заявки;
      - учител: заявките по своите мисии; потвърждава (approve) или отказва (reject).
    """

    serializer_class = ClaimSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # при генериране на документацията няма потребител
            return Claim.objects.none()
        user = self.request.user
        claims = Claim.objects.select_related("mission", "student")
        if user.is_student:
            return claims.filter(student=user)
        if user.is_teacher:
            return claims.filter(mission__in=missions_reviewed_by(user))
        return claims  # администратор

    def _review(self, request, review_function):
        claim = self.get_object()
        data = ReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = review_function(claim, request.user, data.validated_data["comment"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "claim": ClaimSerializer(result.claim).data,
            "xp": result.xp,
            "coins": result.coins,
            "new_level": result.new_level.number if result.new_level else None,
        })

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsTeacher],
            serializer_class=ReviewSerializer)
    def approve(self, request, pk=None):
        return self._review(request, approve_claim)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsTeacher],
            serializer_class=ReviewSerializer)
    def reject(self, request, pk=None):
        return self._review(request, reject_claim)


class MyStatsView(APIView):
    """XP, ниво и монети на влезлия ученик."""

    permission_classes = [IsAuthenticated, IsStudent]

    @extend_schema(responses=StatsSerializer)
    def get(self, request):
        return Response(StatsSerializer(student_stats(request.user)).data)


class MyBadgesView(APIView):
    """Всички значки и докъде е стигнал влезлият ученик до всяка (Ф16)."""

    permission_classes = [IsAuthenticated, IsStudent]

    @extend_schema(responses=BadgeCardSerializer(many=True))
    def get(self, request):
        return Response(BadgeCardSerializer(badge_cards(request.user), many=True).data)


class NotificationsView(APIView):
    """Последните известия на влезлия потребител и колко от тях са непрочетени (Ф15)."""

    @extend_schema(responses=inline_serializer("Notifications", fields={
        "unread": serializers.IntegerField(),
        "items": NotificationSerializer(many=True),
    }))
    def get(self, request):
        return Response({
            "unread": unread_count(request.user),
            "items": NotificationSerializer(recent_for(request.user), many=True).data,
        })


class NotificationsReadView(APIView):
    """Отбелязва всички известия като прочетени."""

    @extend_schema(request=None, responses=inline_serializer("NotificationsRead", fields={
        "marked": serializers.IntegerField(),
    }))
    def post(self, request):
        return Response({"marked": mark_all_read(request.user)})


class BonusView(APIView):
    """Учителят дава бонус XP без мисия (с причина и в лимитите от настройките)."""

    permission_classes = [IsAuthenticated, IsTeacher]

    @extend_schema(request=BonusRequestSerializer, responses=inline_serializer("BonusGiven", fields={
        "xp": serializers.IntegerField(), "coins": serializers.IntegerField(), "bonus_left": serializers.IntegerField(),
    }))
    def post(self, request):
        data = BonusRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        student = get_object_or_404(User, pk=data.validated_data["student"], role=User.Role.STUDENT)
        try:
            coins = give_bonus(request.user, student, data.validated_data["xp"], data.validated_data["reason"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"xp": data.validated_data["xp"], "coins": coins, "bonus_left": bonus_left_this_week(request.user)},
                        status=status.HTTP_201_CREATED)


class BadgeGiftView(APIView):
    """Учителят дава значка, която се дава ръчно (напр. „Звезда на седмицата“)."""

    permission_classes = [IsAuthenticated, IsTeacher]

    @extend_schema(request=BadgeGiftRequestSerializer, responses=inline_serializer("BadgeGiven", fields={
        "badge": serializers.CharField(), "student": serializers.CharField(),
    }))
    def post(self, request):
        data = BadgeGiftRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        student = get_object_or_404(User, pk=data.validated_data["student"], role=User.Role.STUDENT)
        badge = get_object_or_404(Badge, pk=data.validated_data["badge"])
        try:
            give_badge(request.user, student, badge, data.validated_data["note"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"badge": badge.name, "student": student.nickname}, status=status.HTTP_201_CREATED)


class PrivilegeViewSet(viewsets.ReadOnlyModelViewSet):
    """Магазинът: привилегиите в продажба. Ученикът купува с POST /api/privileges/<id>/buy/."""

    serializer_class = PrivilegeSerializer

    def get_queryset(self):
        return active_privileges()

    @extend_schema(request=None, responses=PurchaseSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsStudent])
    def buy(self, request, pk=None):
        privilege = self.get_object()
        try:
            purchase = buy_privilege(request.user, privilege)
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)


class PurchaseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Купени привилегии.
      - ученик: своите покупки;
      - учител: неизползваните покупки; отбелязва използвана с POST /api/purchases/<id>/use/.
    """

    serializer_class = PurchaseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # при генериране на документацията няма потребител
            return Purchase.objects.none()
        user = self.request.user
        if user.is_student:
            return Purchase.objects.filter(student=user).select_related("privilege", "student")
        return unused_purchases()

    @extend_schema(request=None, responses=PurchaseSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsTeacher])
    def use(self, request, pk=None):
        purchase = self.get_object()
        try:
            purchase = mark_purchase_used(purchase, request.user)
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PurchaseSerializer(purchase).data)


class LeaderboardView(APIView):
    """Класации по гилдии, класове и ученици – само с псевдоними (Ф7)."""

    @extend_schema(responses=inline_serializer("Leaderboard", fields={
        "guilds": RankingRowSerializer(many=True),
        "classes": RankingRowSerializer(many=True),
        "students": RankingRowSerializer(many=True),
    }), parameters=[
        OpenApiParameter("guild", int, description="само ученици от тази гилдия"),
        OpenApiParameter("class", int, description="само ученици от този клас"),
        OpenApiParameter("period", str, enum=["all", "week"], description="week – само XP от тази седмица"),
    ])
    def get(self, request):
        guild = request.query_params.get("guild", "")
        school_class = request.query_params.get("class", "")
        tables = leaderboard.rankings(
            "week" if request.query_params.get("period") == "week" else "all",
            guild_id=int(guild) if guild.isdigit() else None,
            class_id=int(school_class) if school_class.isdigit() else None,
        )
        return Response({name: RankingRowSerializer(rows, many=True).data for name, rows in tables.items()})


# ---------- Асистент и справки ----------

class AssistantAskView(APIView):
    """Въпрос към асистента. Ползва се от чата в браузъра (static/js/assistant-chat.js)."""

    @extend_schema(request=QuestionSerializer, responses=AnswerSerializer)
    def post(self, request):
        data = QuestionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            answer = ask(request.user, data.validated_data["question"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except AssistantError as error:
            # Асистентът е изключен, недостъпен или е достигнат лимитът – ясно съобщение.
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(AnswerSerializer({"answer": answer.text, "tool": answer.tool, "data": answer.data}).data)


class MissionDraftView(APIView):
    """Чернова на мисия от асистента (Ф11). Връща данни за формата – нищо не се записва."""

    permission_classes = [IsAuthenticated, IsTeacher]

    @extend_schema(request=IdeaSerializer, responses=DraftSerializer)
    def post(self, request):
        data = IdeaSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            draft = draft_mission(request.user, data.validated_data["idea"])
        except GameRuleError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except AssistantError as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(DraftSerializer(draft).data)


class ReportView(APIView):
    """
    Справки по разписанието без асистента (Ф17, Ф18, Ф22).
    Пример: GET /api/reports/free_rooms/?day=сряда&period=3
    """

    @extend_schema(responses=OpenApiTypes.OBJECT, parameters=[
        OpenApiParameter("teacher", str), OpenApiParameter("class_name", str),
        OpenApiParameter("day", str), OpenApiParameter("period", str),
    ])
    def get(self, request, report):
        params = {key: request.query_params.get(key, "") for key in ("teacher", "class_name", "day", "period")}
        try:
            return Response(queries.run_report(request.user, report, params))
        except queries.QueryError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
