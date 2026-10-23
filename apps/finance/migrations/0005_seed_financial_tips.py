from django.db import migrations


TIPS = [
    (
        "Plan spending for the week",
        "Budgeting",
        "Choose a realistic amount for food, transport, and other weekly costs. Check your spending during the week so you can adjust early.",
    ),
    (
        "Save a little from each payment",
        "Saving",
        "When money comes in, move a small amount toward a savings goal before using the rest. A regular small contribution can build a useful habit.",
    ),
    (
        "Review recurring costs",
        "Spending",
        "Check subscriptions and regular payments from time to time. Cancel services you no longer use and include the remaining costs in your budget.",
    ),
    (
        "Check your budget before month end",
        "Budgeting",
        "Compare what you have spent with each category limit during the month. If one category is close to its limit, plan the remaining spending carefully.",
    ),
]


def add_tips(apps, schema_editor):
    FinancialTip = apps.get_model("finance", "FinancialTip")
    for title, category, content in TIPS:
        FinancialTip.objects.get_or_create(
            title=title,
            defaults={"category": category, "content": content, "is_active": True},
        )


def remove_tips(apps, schema_editor):
    FinancialTip = apps.get_model("finance", "FinancialTip")
    FinancialTip.objects.filter(title__in=[tip[0] for tip in TIPS]).delete()


class Migration(migrations.Migration):
    dependencies = [("finance", "0004_financialtip")]

    operations = [migrations.RunPython(add_tips, remove_tips)]
