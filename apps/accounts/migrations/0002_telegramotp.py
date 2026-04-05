from django.db import migrations, models
import phonenumber_field.modelfields


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramOTP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone_number", phonenumber_field.modelfields.PhoneNumberField(db_index=True, max_length=128, region=None)),
                ("request_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("is_used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Telegram OTP",
                "verbose_name_plural": "Telegram OTPs",
                "db_table": "accounts_telegram_otps",
            },
        ),
    ]
