import os
import json
import django
from django.utils import timezone
from datetime import datetime
from django.db import transaction

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from prices.models import PriceList, PriceListFile, BotUser

def clear_all_data():
    PriceListFile.objects.all().delete()
    PriceList.objects.all().delete()
    BotUser.objects.all().delete()
    print('All price lists, files, and users deleted.')

def clear_all_users():
    BotUser.objects.all().delete()
    print('All users deleted.')

@transaction.atomic
def import_price_lists():
    with open('data/files.json', encoding='utf-8') as f:
        data = json.load(f)
    data = list(reversed(data))  # Reverse the order
    for rank, item in enumerate(data):
        title = item.get('caption', f'لیست قیمت {rank+1}')
        price_list = PriceList.objects.create(
            title=title,
            rank=rank
        )
        for idx, file_id in enumerate(item.get('file_ids', [])):
            PriceListFile.objects.create(
                price_list=price_list,
                telegram_file_id=file_id,
                file_type='document',
                name=f'فایل شماره {idx+1}'
            )
    print('Price lists imported.')

@transaction.atomic
def import_users():
    with open('data/users.json', encoding='utf-8') as f:
        users = json.load(f)
    for user in users:
        user_id = user.get('user_id') or user.get('chat_id')
        if user_id is None:
            continue
        try:
            user_id = int(user_id)
        except Exception:
            continue
        first_name = user.get('first_name', '')
        username = user.get('username', '')
        BotUser.objects.get_or_create(
            user_id=user_id,
            defaults={
                'first_name': first_name,
                'username': username
            }
        )
    print('Users imported.')

if __name__ == '__main__':
    clear_all_users()
    import_users()
    print('Done.')
