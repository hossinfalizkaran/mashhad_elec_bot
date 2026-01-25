from import_export import resources, fields
from .models import Business

class BusinessResource(resources.ModelResource):
    # نگاشت دقیق فیلدها (نام در فایل JSON : نام در مدل جنگو)
    shop_name = fields.Field(attribute='shop_name', column_name='shopName')
    management = fields.Field(attribute='management', column_name='management')
    address = fields.Field(attribute='address', column_name='address')
    landline = fields.Field(attribute='landline', column_name='landline')
    mobile = fields.Field(attribute='mobile', column_name='mobile')
    activity = fields.Field(attribute='activity', column_name='activity')

    class Meta:
        model = Business
        # بسیار مهم: فیلد id فایل JSON را نادیده می‌گیریم تا با id دیتابیس جنگو قاطی نشود
        exclude = ('id', ) 
        # فیلدهایی که اجازه ورود دارند
        fields = ('shop_name', 'management', 'address', 'landline', 'mobile', 'activity')
        # تشخیص تکراری بودن بر اساس نام فروشگاه
        import_id_fields = ('shop_name',)

    def before_import_row(self, row, **kwargs):
        # تمیز کردن داده‌ها: اگر تلفن ثابت رشته "null" بود، آن را خالی کن
        if row.get('landline') == "null":
            row['landline'] = ""