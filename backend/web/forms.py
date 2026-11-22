"""Формите в страниците за ученици и учители."""
from django import forms

from economy.models import GameSettings
from missions.evidence import ACCEPT
from missions.models import Mission
from missions.services import EVIDENCE_MAX_LENGTH


class MissionForm(forms.ModelForm):
    """Учителят създава или редактира мисия (Ф3). Правилата са в Mission.clean()."""

    class Meta:
        model = Mission
        fields = ["title", "description", "criteria", "guild", "xp", "deadline", "hints_allowed", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "criteria": forms.Textarea(attrs={"rows": 3}),
            # Календар с час в браузъра
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_xp = GameSettings.load().max_xp_per_mission
        self.fields["xp"].help_text = f"Най-много {max_xp} XP."
        if self.instance._state.adding:
            # Нова мисия винаги е активна – полето е само за редакция.
            del self.fields["is_active"]


class ReviewForm(forms.Form):
    """Учителят потвърждава или отказва заявка (Ф5)."""

    APPROVE = "approve"
    REJECT = "reject"

    decision = forms.ChoiceField(choices=[(APPROVE, "Потвърди"), (REJECT, "Откажи")])
    comment = forms.CharField(
        label="Коментар", required=False, max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Коментар към ученика (по желание)"}),
    )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Поле за няколко файла наведнъж (както е в документацията на Django)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)] if data else []


class ClaimForm(forms.Form):
    """Ученикът заявява изпълнение с доказателство (Ф4): текст и/или снимки и PDF."""

    evidence = forms.CharField(
        label="Доказателство",
        max_length=EVIDENCE_MAX_LENGTH, required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Кратко описание или връзка (например към видео)"}),
    )
    files = MultipleFileField(label="Снимки или PDF", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rules = GameSettings.load()
        if not rules.evidence_max_files:
            del self.fields["files"]
            return
        self.fields["files"].widget.attrs["accept"] = ACCEPT
        self.fields["files"].help_text = (
            f"До {rules.evidence_max_files} файла по {rules.evidence_max_mb} MB: снимки (JPG, PNG, WebP) или PDF. "
            "За видео сложи връзка в текста (YouTube, Google Drive)."
        )


class NicknameForm(forms.Form):
    """Ученикът сменя псевдонима си. Правилата са в accounts/nicknames.py."""

    nickname = forms.CharField(label="Нов псевдоним", max_length=20)


class StudentChoiceField(forms.ModelChoiceField):
    """Ученик: „Иван Петров (Феникс), 11Б“ – учителят знае истинските имена."""

    def __init__(self, **kwargs):
        from accounts.models import User

        queryset = User.objects.filter(role=User.Role.STUDENT, is_active=True).select_related(
            "school_class").order_by("school_class__name", "last_name", "first_name", "nickname")
        super().__init__(queryset=queryset, label="Ученик", empty_label="Избери ученик", **kwargs)

    def label_from_instance(self, student):
        name = student.get_full_name() or student.email
        return f"{name} ({student.nickname}), {student.school_class or 'без клас'}"


class BonusForm(forms.Form):
    """Бонус XP без мисия. Лимитите се проверяват в economy/services.py → give_bonus."""

    student = StudentChoiceField()
    xp = forms.IntegerField(label="XP", min_value=1)
    reason = forms.CharField(label="За какво", max_length=200,
                             widget=forms.TextInput(attrs={"placeholder": "напр. Помощ при организирането на концерта"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit = GameSettings.load().bonus_max_xp
        self.fields["xp"].max_value = limit
        self.fields["xp"].widget.attrs["max"] = limit
        self.fields["xp"].help_text = f"От 1 до {limit} XP наведнъж."


class BadgeGiftForm(forms.Form):
    """Значка, която се дава от учител (в администрацията: правило „Дава се от учител“)."""

    student = StudentChoiceField()
    badge = forms.ModelChoiceField(queryset=None, label="Значка", empty_label="Избери значка")
    note = forms.CharField(label="За какво (по желание)", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        from badges.models import Badge

        super().__init__(*args, **kwargs)
        self.fields["badge"].queryset = Badge.objects.filter(rule=Badge.Rule.MANUAL, is_active=True)
