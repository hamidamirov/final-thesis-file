from django.db import migrations


def create_platform_administrator_role(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model("auth", "User")
    group, _ = Group.objects.using(database).get_or_create(name="Platform administrators")
    grants = {
        ("auth", "user"): ("view", "change"),
        ("finance", "financialtip"): ("view", "add", "change", "delete"),
        ("finance", "savingchallenge"): ("view", "add", "change", "delete"),
        ("finance", "studentoffer"): ("view", "add", "change", "delete"),
        ("finance", "studentverificationrequest"): ("view", "change"),
        ("finance", "accountdeletionrequest"): ("view", "change"),
        ("axes", "accessattempt"): ("view",),
        ("axes", "accesslog"): ("view",),
        ("axes", "accessfailurelog"): ("view",),
    }
    permissions = []
    for (app_label, model), actions in grants.items():
        content_type, _ = ContentType.objects.using(database).get_or_create(app_label=app_label, model=model)
        for action in actions:
            permission, _ = Permission.objects.using(database).get_or_create(
                content_type=content_type, codename=f"{action}_{model}",
                defaults={"name": f"Can {action} {model}"},
            )
            permissions.append(permission)
    for model, codename, name in (
        ("studentverificationrequest", "review_student_status", "Can review student status"),
        ("accountdeletionrequest", "review_account_deletion", "Can review account deletion requests"),
    ):
        content_type = ContentType.objects.using(database).get(app_label="finance", model=model)
        permission, _ = Permission.objects.using(database).get_or_create(
            content_type=content_type, codename=codename, defaults={"name": name},
        )
        permissions.append(permission)
    group.permissions.set(permissions)
    for user in User.objects.using(database).filter(is_staff=True, is_superuser=False).iterator():
        user.groups.add(group)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_admin_privacy"),
        ("finance", "0016_admin_privacy"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [
        migrations.RunPython(create_platform_administrator_role, migrations.RunPython.noop),
    ]
