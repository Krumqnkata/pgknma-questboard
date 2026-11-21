from django.test import TestCase

from .models import GameSettings, Level, Privilege


class GameSettingsTests(TestCase):
    def test_default_rules_from_the_innovation(self):
        rules = GameSettings.load()
        self.assertEqual(rules.xp_per_coin, 50)
        self.assertEqual(rules.weekly_coin_limit, 5)

    def test_there_is_only_one_settings_row(self):
        GameSettings(xp_per_coin=40).save()
        GameSettings(xp_per_coin=60).save()
        self.assertEqual(GameSettings.objects.count(), 1)
        self.assertEqual(GameSettings.load().xp_per_coin, 60)


class InitialDataTests(TestCase):
    def test_levels_start_from_zero_xp(self):
        self.assertEqual(Level.objects.order_by("min_xp").first().min_xp, 0)

    def test_shop_has_deadline_pass_and_hint_token(self):
        codes = set(Privilege.objects.values_list("code", flat=True))
        self.assertTrue({"deadline_pass", "hint_token"} <= codes)
