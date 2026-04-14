from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobcategory",
            name="icon",
            field=models.FileField(
                blank=True,
                help_text="Upload an SVG or image file",
                upload_to="categories/icons/",
            ),
        ),
    ]
