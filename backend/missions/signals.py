"""Когато файл към доказателство или мисия се изтрие от базата, изтриваме и самия файл от диска."""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import EvidenceFile, MissionFile


@receiver(post_delete, sender=EvidenceFile)
@receiver(post_delete, sender=MissionFile)
def delete_evidence_file(sender, instance, **kwargs):
    if instance.file:
        # Само ако транзакцията мине – иначе записът остава, а файлът би липсвал.
        transaction.on_commit(lambda: instance.file.delete(save=False))
