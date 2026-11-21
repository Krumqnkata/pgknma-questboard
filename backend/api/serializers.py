import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from economy.models import Privilege, Purchase
from missions.models import Claim, Mission
from missions.services import EVIDENCE_MAX_LENGTH


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


class ClaimSerializer(serializers.ModelSerializer):
    mission_title = serializers.CharField(source="mission.title", read_only=True)
    student = serializers.StringRelatedField()

    class Meta:
        model = Claim
        fields = ["id", "mission", "mission_title", "student", "evidence", "status",
                  "submitted_at", "reviewed_at", "review_comment"]
        read_only_fields = fields


class ClaimCreateSerializer(serializers.Serializer):
    evidence = serializers.CharField(max_length=EVIDENCE_MAX_LENGTH)


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
