from django.db import models

class Business(models.Model):
    shop_name = models.CharField(max_length=255, verbose_name="نام فروشگاه")
    management = models.CharField(max_length=255, null=True, blank=True, verbose_name="مدیریت")
    address = models.TextField(null=True, blank=True, verbose_name="آدرس")
    landline = models.CharField(max_length=50, blank=True, null=True, verbose_name="تلفن ثابت")
    mobile = models.CharField(max_length=50, blank=True, null=True, verbose_name="تلفن همراه")
    activity = models.TextField(null=True, blank=True, verbose_name="زمینه فعالیت")
    
    rank = models.IntegerField(default=0, verbose_name="رتبه")
    owner_telegram_id = models.BigIntegerField(null=True, blank=True, verbose_name="آیدی تلگرام مالک")
    is_verified = models.BooleanField(default=False, verbose_name="تایید شده؟")

    def __str__(self):
        return self.shop_name or "بدون نام"

class ClaimRequest(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField()
    username = models.CharField(max_length=255, null=True, blank=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    verification_code = models.CharField(max_length=6, null=True, blank=True)
    status = models.CharField(max_length=20, default='pending') # pending, completed
    created_at = models.DateTimeField(auto_now_add=True)