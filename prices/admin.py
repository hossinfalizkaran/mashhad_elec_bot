from django.contrib import admin
from .models import PriceList, PriceListFile, BotUser, Log
from django.utils.html import format_html
from django.conf import settings
import os
from django.http import FileResponse
import json
from django.contrib import messages

class PriceListFileInline(admin.TabularInline):
    model = PriceListFile
    extra = 0
    fields = ("name", "file_type", "telegram_file_id")
    readonly_fields = ()

@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("title", "rank", "updated_at")
    search_fields = ("title",)
    inlines = [PriceListFileInline]

@admin.register(PriceListFile)
class PriceListFileAdmin(admin.ModelAdmin):
    list_display = ("name", "file_type", "price_list", "download_link")
    search_fields = ("name", "file_type")

    def download_link(self, obj):
        # فرض بر این است که فایل‌ها در media/pricelists/ ذخیره شده‌اند و نام فایل از name یا فیلد دیگر قابل استخراج است
        # اگر فایل واقعی روی سرور دارید، مسیر را بر اساس مدل خود اصلاح کنید
        file_path = os.path.join(settings.MEDIA_URL, 'pricelists', obj.name)
        return format_html('<a href="{}" download>دانلود</a>', file_path)
    download_link.short_description = "دانلود فایل"

@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ("user_id", "first_name", "username", "joined_at")
    search_fields = ("user_id", "first_name", "username")

def clear_user_logs_and_states(modeladmin, request, queryset):
    Log.objects.all().delete()
    user_states_path = os.path.join(settings.BASE_DIR, 'data', 'user_states.json')
    with open(user_states_path, 'w', encoding='utf-8') as f:
        f.write('[]')
    messages.success(request, 'همه لاگ‌ها و وضعیت کاربران پاک‌سازی شد.')

clear_user_logs_and_states.short_description = 'پاک‌سازی همه پیام‌ها و وضعیت کاربران'

@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ("user_id", "first_name", "username", "event_type", "timestamp")
    search_fields = ("user_id", "first_name", "username", "event_type")
    actions = [clear_user_logs_and_states]

