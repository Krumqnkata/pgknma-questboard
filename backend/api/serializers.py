import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
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
