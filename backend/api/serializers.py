from rest_framework import serializers

from accounts.models import User


class MeSerializer(serializers.ModelSerializer):
    """Данни за влезлия потребител."""

    school_class = serializers.StringRelatedField()
    guild = serializers.StringRelatedField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "nickname", "school_class", "guild"]
