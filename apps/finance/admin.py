from django.contrib import admin

from .models import Budget, Transaction


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("month", "user", "category", "amount")
    list_filter = ("month", "category")
    search_fields = ("user__username", "category")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "type", "category", "amount")
    list_filter = ("type", "date", "category")
    search_fields = ("user__username", "category", "note")
    date_hierarchy = "date"
