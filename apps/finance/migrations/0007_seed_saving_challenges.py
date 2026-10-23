from django.db import migrations


CHALLENGES = [
    (
        "Plan a no-spend day",
        "Choose one day to avoid non-essential purchases. Record any spending and note what helped you stick to the plan.",
        7,
    ),
    (
        "Bring lunch from home",
        "Prepare lunch at home for five study days and compare the cost with your usual lunch spending.",
        7,
    ),
    (
        "Make a weekly savings contribution",
        "Choose an affordable amount and add it to one of your savings goals each week for four weeks.",
        28,
    ),
]


def add_challenges(apps, schema_editor):
    SavingChallenge = apps.get_model("finance", "SavingChallenge")
    for title, description, duration_days in CHALLENGES:
        SavingChallenge.objects.get_or_create(
            title=title,
            defaults={
                "description": description,
                "duration_days": duration_days,
                "is_active": True,
            },
        )


def remove_challenges(apps, schema_editor):
    SavingChallenge = apps.get_model("finance", "SavingChallenge")
    SavingChallenge.objects.filter(title__in=[challenge[0] for challenge in CHALLENGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("finance", "0006_savingchallenge_userchallenge")]

    operations = [migrations.RunPython(add_challenges, remove_challenges)]
