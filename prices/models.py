from django.db import models
import jdatetime
from django.utils import timezone

class PriceList(models.Model):
    title = models.CharField(max_length=255)
    rank = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-rank', '-updated_at']

    def get_jalali_date(self):
        local_dt = timezone.localtime(self.updated_at)
        return jdatetime.datetime.fromgregorian(datetime=local_dt).strftime('%Y/%m/%d - %H:%M')

    def __str__(self):
        return self.title

class PriceListFile(models.Model):
    price_list = models.ForeignKey(PriceList, related_name='files', on_delete=models.CASCADE)
    telegram_file_id = models.CharField(max_length=255, blank=True)
    bale_file_id = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=20)
    name = models.CharField(max_length=255, default="فایل شماره یک")  # افزودن نام فایل

    def __str__(self):
        return f"{self.name} ({self.file_type})"

class BotUser(models.Model):
    user_id = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

# --- مدل جدید برای لاگ ---
class Log(models.Model):
    user_id = models.BigIntegerField()
    first_name = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    event_type = models.CharField(max_length=50)
    event_detail = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} - {self.event_type}"

class BaleUser(models.Model):
    user_id = models.CharField(max_length=64, unique=True)
    first_name = models.CharField(max_length=128, blank=True)
    username = models.CharField(max_length=128, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)