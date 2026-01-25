import json
import random
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from .models import Business, ClaimRequest

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'management', 'rank', 'is_verified', 'owner_telegram_id')
    list_editable = ('rank',)
    search_fields = ('shop_name', 'management', 'activity')
    change_list_template = "admin/business_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [path('import-json/', self.import_json, name='import_json')]
        return custom_urls + urls

    def import_json(self, request):
        if request.method == "POST":
            json_file = request.FILES.get('file')
            try:
                data = json.load(json_file)
                count = 0
                for item in data:
                    s_name = item.get('shopName')
                    if not s_name: continue
                    Business.objects.update_or_create(
                        shop_name=s_name,
                        defaults={
                            'management': item.get('management', ""),
                            'address': item.get('address', ""),
                            'landline': item.get('landline', "") if item.get('landline') != "null" else "",
                            'mobile': item.get('mobile', ""),
                            'activity': item.get('activity', ""),
                        }
                    )
                    count += 1
                self.message_user(request, f"{count} رکورد با موفقیت وارد شد.", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"خطا: {str(e)}", messages.ERROR)
            return redirect("..")
        return render(request, "admin/import_json_form.html")

@admin.register(ClaimRequest)
class ClaimRequestAdmin(admin.ModelAdmin):
    list_display = ('business', 'username', 'telegram_id', 'status', 'verification_code')
    actions = ['approve_claim']

    def approve_claim(self, request, queryset):
        for claim in queryset:
            code = str(random.randint(10000, 99999))
            claim.verification_code = code
            claim.status = 'approved'
            claim.save()
        self.message_user(request, "درخواست‌ها تایید و کدهای جدید تولید شدند.", messages.SUCCESS)
    approve_claim.short_description = "تایید درخواست و تولید کد"