"""Формите в страниците за ученици и учители."""
from django import forms
from django.db.models import Q

from accounts.models import User
from badges.models import Badge
from economy.models import GameSettings, Privilege
from missions.evidence import ACCEPT, ALLOWED_TEXT, prepare_all
from missions.models import TEAM_LIMIT, Mission, MissionFile
from missions.services import EVIDENCE_MAX_LENGTH, GameRuleError, attach_to_mission, parse_nicknames
from quizzes.models import GuildTest, Question


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


class TeacherChoices(forms.ModelMultipleChoiceField):
    def label_from_instance(self, teacher):
        return teacher.get_full_name() or teacher.email


class MissionForm(forms.ModelForm):
    """Учителят създава или редактира мисия (Ф3). Правилата са в Mission.clean()."""

    reviewers = TeacherChoices(
        queryset=User.objects.none(), required=False, label="Заместници при проверката",
        widget=forms.CheckboxSelectMultiple,
        help_text="Учители, които също могат да потвърждават и отказват заявките. "
                  "Ако не изберете никого, проверявате само вие.",
    )
    files = MultipleFileField(label="Файлове към мисията", required=False)
    remove_files = forms.ModelMultipleChoiceField(
        queryset=MissionFile.objects.none(), required=False, label="Махни файлове",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Mission
        fields = ["title", "description", "criteria", "guild", "xp", "deadline", "hints_allowed",
                  "is_group", "team_min", "team_max", "reward_badge", "reward_item", "reviewers", "is_active"]
        widgets = {
            "team_min": forms.NumberInput(attrs={"min": 2, "max": TEAM_LIMIT}),
            "team_max": forms.NumberInput(attrs={"min": 2, "max": TEAM_LIMIT}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "criteria": forms.Textarea(attrs={"rows": 3}),
            # Календар с час в браузъра
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_xp = GameSettings.load().max_xp_per_mission
        self.fields["xp"].help_text = f"Най-много {max_xp} XP."
        if "guild" in self.fields:
            self.fields["guild"].required = True
        if "reward_badge" in self.fields:
            self._setup_rewards()
        self._setup_rest()

    def _setup_rewards(self):
        self.fields["reward_badge"].queryset = Badge.objects.filter(
            Q(rule=Badge.Rule.MISSION, is_active=True) | Q(pk=self.instance.reward_badge_id))
        self.fields["reward_badge"].empty_label = "Без значка"
        self.fields["reward_badge"].help_text = "Получава се само от тази мисия. Нови значки добавя администраторът."
        # Учителят не може да подари обикновена стока от магазина – само предмет за мисии или награда от контрибутор.
        self.fields["reward_item"].queryset = Privilege.objects.filter(
            Q(only_from_mission=True, is_active=True) | Q(kind=Privilege.Kind.SPONSOR, is_active=True)
            | Q(pk=self.instance.reward_item_id)).select_related("sponsor")
        self.fields["reward_item"].empty_label = "Без предмет"
        self.fields["reward_item"].label_from_instance = reward_label

    def _setup_rest(self):
        self.fields["reviewers"].queryset = User.objects.filter(
            role=User.Role.TEACHER, is_active=True).exclude(pk=self.instance.created_by_id)
        self.fields["team_min"].required = self.fields["team_max"].required = False
        rules = GameSettings.load()
        self.fields["files"].widget.attrs["accept"] = ACCEPT
        self.fields["files"].help_text = (f"Указания, образец или плакат – до {rules.evidence_max_files} файла по "
                                          f"{rules.evidence_max_mb} MB: {ALLOWED_TEXT}.")
        if not rules.evidence_max_files:
            del self.fields["files"]
        own_files = MissionFile.objects.filter(mission=self.instance) if self.instance.pk else MissionFile.objects.none()
        if own_files:
            self.fields["remove_files"].queryset = own_files
        else:
            del self.fields["remove_files"]
        if self.instance._state.adding:
            # Нова мисия винаги е активна – полето е само за редакция.
            del self.fields["is_active"]

    # Празно поле за размер на отбора = стойността по подразбиране.
    def clean_team_min(self):
        return self.cleaned_data.get("team_min") or Mission._meta.get_field("team_min").default

    def clean_team_max(self):
        return self.cleaned_data.get("team_max") or Mission._meta.get_field("team_max").default

    def clean_files(self):
        """Файловете се проверяват още тук, за да се покаже грешката до полето."""
        try:
            self.prepared_files = prepare_all(self.cleaned_data.get("files") or [], GameSettings.load())
        except GameRuleError as error:
            raise forms.ValidationError(str(error))
        return self.cleaned_data.get("files")

    def save(self, commit=True):
        mission = super().save(commit)
        for record in self.cleaned_data.get("remove_files") or []:
            record.delete()
        attach_to_mission(mission, getattr(self, "prepared_files", []))
        return mission


class HomeworkForm(MissionForm):
    """Домашна работа: мисия за избрани класове, без гилдия и без специални награди."""

    class Meta(MissionForm.Meta):
        fields = ["title", "subject", "school_classes", "description", "criteria", "xp", "deadline", "hints_allowed",
                  "is_group", "team_min", "team_max", "reviewers", "is_active"]
        widgets = {**MissionForm.Meta.widgets, "school_classes": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit = GameSettings.load().max_xp_per_homework
        self.fields["xp"].help_text = f"За предадена и приета домашна, най-много {limit} XP. Не е оценка."
        self.fields["subject"].required = self.fields["school_classes"].required = True
        self.fields["criteria"].label = "Кога се приема"


def reward_label(item):
    if item.kind == Privilege.Kind.SPONSOR:
        left = "" if item.left is None else f", остават {item.left}"
        return f"{item.name} ({item.sponsor}{left})"
    return f"{item.name} ({item.get_kind_display().lower()})"


class ReviewForm(forms.Form):
    """Учителят потвърждава или отказва заявка (Ф5)."""

    APPROVE = "approve"
    REJECT = "reject"

    decision = forms.ChoiceField(choices=[(APPROVE, "Потвърди"), (REJECT, "Откажи")])
    comment = forms.CharField(
        label="Коментар", required=False, max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Коментар към ученика (по желание)"}),
    )


class ClaimForm(forms.Form):
    """Ученикът заявява изпълнение с доказателство (Ф4): текст и/или файлове, а при отборна мисия – и съотборниците."""

    teammates = forms.CharField(
        label="Съотборници", required=False, max_length=400,
        widget=forms.TextInput(attrs={"placeholder": "Комета, Вихър", "autocomplete": "off"}),
    )
    evidence = forms.CharField(
        label="Доказателство",
        max_length=EVIDENCE_MAX_LENGTH, required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Кратко описание или връзка (например към видео)"}),
    )
    files = MultipleFileField(label="Файлове", required=False)

    def __init__(self, *args, mission=None, **kwargs):
        super().__init__(*args, **kwargs)
        if mission is None or not mission.is_group:
            del self.fields["teammates"]
        else:
            self.fields["teammates"].help_text = (
                f"Псевдонимите им, разделени със запетая. Отборът е от {mission.team_min} до "
                f"{mission.team_max} ученици заедно с теб. Всеки получава известие и пълната награда."
            )
        rules = GameSettings.load()
        if not rules.evidence_max_files:
            del self.fields["files"]
            return
        self.fields["files"].widget.attrs["accept"] = ACCEPT
        self.fields["files"].help_text = (
            f"До {rules.evidence_max_files} файла по {rules.evidence_max_mb} MB: {ALLOWED_TEXT}. "
            "За видео сложи връзка в текста (YouTube, Google Drive)."
        )


    def clean_teammates(self):
        return parse_nicknames(self.cleaned_data.get("teammates"))


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


class GuildTestForm(forms.ModelForm):
    class Meta:
        model = GuildTest
        fields = ["guild", "kind", "title", "description", "questions_count", "seconds", "pass_percent", "xp",
                  "retry_days", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["kind", "text", "answers", "seconds"]
        widgets = {"text": forms.Textarea(attrs={"rows": 2}), "answers": forms.Textarea(attrs={"rows": 5})}


class QuestionDraftForm(forms.Form):
    topic = forms.CharField(label="Тема", min_length=3, max_length=300,
                            widget=forms.TextInput(attrs={"placeholder": "напр. основи на Python: цикли и условия"}))
    count = forms.IntegerField(label="Колко въпроса", min_value=1, max_value=10, initial=5)


class SessionForm(forms.Form):
    minutes = forms.IntegerField(label="Минути", min_value=5, max_value=90, initial=15)
