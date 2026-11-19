from django.conf import settings
from django.db import models


class AdminActivityPreferences(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cleared_through_id = models.PositiveBigIntegerField(default=0)
    hidden_action_ids = models.JSONField(default=list, blank=True)

    class Meta:
        permissions = [
            ("view_full_email", "Can view full email addresses"),
            ("delete_admin_history", "Can permanently delete admin history"),
        ]
