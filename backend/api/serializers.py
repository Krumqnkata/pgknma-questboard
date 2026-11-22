import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from economy.models import Privilege, Purchase
from missions.models import Claim, EvidenceFile, Mission
from missions.services import EVIDENCE_MAX_LENGTH
from notifications.models import Notification


class MeSerializer(serializers.ModelSerializer):
    """Данни за влезлия потребител."""

    school_class = serializers.StringRelatedField()
    guild = serializers.StringRelatedField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "nickname", "school_class", "guild"]


class MissionSerializer(serializers.ModelSerializer):
    guild_name = serializers.CharField(source="guild.name", read_only=True)
    created_by = serializers.StringRelatedField()

    class Meta:
        model = Mission
        fields = ["id", "title", "description", "criteria", "guild", "guild_name", "xp", "deadline",
                  "hints_allowed", "is_active", "created_by", "created_at"]
        read_only_fields = ["created_by", "created_at"]

    def validate(self, attrs):
        """Пуска същите правила като формите – Mission.clean()."""
        mission = copy.copy(self.instance) if self.instance else Mission()
        for field, value in attrs.items():
            setattr(mission, field, value)
        try:
            mission.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict)
        return attrs


class EvidenceFileSerializer(serializers.ModelSerializer):
    url = serializers.CharField(source="get_absolute_url", read_only=True,
                                help_text="Отваря се само от ученика, учителя на мисията и администратора.")

    class Meta:
        model = EvidenceFile
        fields = ["id", "kind", "original_name", "size", "url"]
        read_only_fields = fields


class ClaimSerializer(serializers.ModelSerializer):
    mission_title = serializers.CharField(source="mission.title", read_only=True)
    student = serializers.StringRelatedField()
    files = EvidenceFileSerializer(many=True, read_only=True)

    class Meta:
        model = Claim
        fields = ["id", "mission", "mission_title", "student", "evidence", "files", "status",
                  "submitted_at", "reviewed_at", "review_comment"]
        read_only_fields = fields


class ClaimCreateSerializer(serializers.Serializer):
    """JSON с текст или multipart/form-data с текст и файлове (полето files може да се повтаря)."""

    evidence = serializers.CharField(max_length=EVIDENCE_MAX_LENGTH, required=False, allow_blank=True, default="")
    files = serializers.ListField(child=serializers.FileField(), required=False,
                                  help_text="Снимки (JPG, PNG, WebP) или PDF.")


class ReviewSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class StatsSerializer(serializers.Serializer):
    """XP, ниво и монети на ученика."""

    xp = serializers.IntegerField()
    level = serializers.IntegerField(source="level.number", allow_null=True)
    level_title = serializers.CharField(source="level.title", allow_null=True)
    next_level_xp = serializers.IntegerField(source="next_level.min_xp", allow_null=True)
    xp_to_next_level = serializers.IntegerField()
    coins = serializers.IntegerField()
    coins_this_week = serializers.IntegerField()
    weekly_limit = serializers.IntegerField()


class PrivilegeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Privilege
        fields = ["id", "code", "name", "description", "price"]


class PurchaseSerializer(serializers.ModelSerializer):
    privilege = serializers.CharField(source="privilege.name")
    student = serializers.CharField(source="student.nickname")

    class Meta:
        model = Purchase
        fields = ["id", "privilege", "student", "price_paid", "purchased_at", "used_at"]


class RankingRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    name = serializers.CharField()
    xp = serializers.IntegerField()
    members = serializers.IntegerField()
    average = serializers.IntegerField()
    guild = serializers.CharField()
    level = serializers.IntegerField(source="level.number", allow_null=True, default=None)
    movement = serializers.IntegerField(help_text="Места нагоре (+) или надолу (-) от началото на седмицата.")
    title = serializers.CharField(source="user.shown_title.name", allow_null=True, default=None)


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=500)


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    tool = serializers.CharField(allow_null=True)
    data = serializers.DictField()


class IdeaSerializer(serializers.Serializer):
    idea = serializers.CharField(min_length=5, max_length=1000)


class DraftSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    criteria = serializers.CharField()
    guild = serializers.IntegerField(allow_null=True)
    xp = serializers.IntegerField()


class HintSerializer(serializers.Serializer):
    hint = serializers.CharField(source="text")
    created_at = serializers.DateTimeField()


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "text", "link", "created_at", "is_read"]


class BadgeCardSerializer(serializers.Serializer):
    """Значка и докъде е стигнал ученикът до нея."""

    name = serializers.CharField(source="badge.name")
    description = serializers.CharField(source="badge.description")
    icon = serializers.CharField(source="badge.icon")
    rule = serializers.CharField(source="badge.rule")
    threshold = serializers.IntegerField(source="badge.threshold")
    value = serializers.IntegerField()
    earned = serializers.BooleanField()


class BonusRequestSerializer(serializers.Serializer):
    student = serializers.IntegerField(help_text="Номерът на ученика.")
    xp = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=200)


class BadgeGiftRequestSerializer(serializers.Serializer):
    student = serializers.IntegerField(help_text="Номерът на ученика.")
    badge = serializers.IntegerField(help_text="Значка с правило „Дава се от учител“.")
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
