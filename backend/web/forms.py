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
