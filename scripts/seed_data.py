"""
Seed data management command.
Usage: python manage.py seed_data [--users 20] [--jobs 50] [--reset]

Creates realistic demo data for development and staging environments.
"""

import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


CATEGORIES = [
    {"name": "Cleaning", "slug": "cleaning", "icon": "🧹", "sort_order": 1},
    {"name": "Delivery", "slug": "delivery", "icon": "🚚", "sort_order": 2},
    {"name": "Moving", "slug": "moving", "icon": "📦", "sort_order": 3},
    {"name": "Repair", "slug": "repair", "icon": "🔧", "sort_order": 4},
    {"name": "Assembly", "slug": "assembly", "icon": "🪛", "sort_order": 5},
    {"name": "Gardening", "slug": "gardening", "icon": "🌿", "sort_order": 6},
    {"name": "Painting", "slug": "painting", "icon": "🎨", "sort_order": 7},
    {"name": "IT Help", "slug": "it-help", "icon": "💻", "sort_order": 8},
    {"name": "Security", "slug": "security", "icon": "🔒", "sort_order": 9},
    {"name": "Cooking", "slug": "cooking", "icon": "🍳", "sort_order": 10},
]

# Tashkent area coordinates
TASHKENT_LOCATIONS = [
    (41.2995, 69.2401, "Yunusabad, Tashkent"),
    (41.3111, 69.2797, "Chilonzor, Tashkent"),
    (41.2856, 69.2037, "Sergeli, Tashkent"),
    (41.3456, 69.3167, "Mirzo Ulugbek, Tashkent"),
    (41.3234, 69.2987, "Shaykhontohur, Tashkent"),
    (41.2711, 69.2134, "Uchtepa, Tashkent"),
    (41.3089, 69.2501, "Yakkasaray, Tashkent"),
    (41.2967, 69.3345, "Bektemir, Tashkent"),
    (41.3567, 69.2234, "Almazar, Tashkent"),
    (41.2789, 69.3012, "Olmazor, Tashkent"),
]

UZBEK_NAMES = [
    "Alisher Umarov", "Dilnoza Yusupova", "Bobur Karimov",
    "Malika Rakhimova", "Jasur Abdullayev", "Nilufar Toshmatova",
    "Sardor Mirzayev", "Feruza Nazarova", "Ulugbek Xasanov",
    "Zulfiya Ergasheva", "Mansur Begmatov", "Shakhnoza Qodirova",
    "Nodir Ismoilov", "Gulnora Tursunova", "Behruz Salimov",
    "Mohira Yunusova", "Akbar Ahmedov", "Shahnoza Olimova",
    "Timur Rustamov", "Nargiza Xolmatova",
]

JOB_TEMPLATES = [
    ("Deep apartment cleaning needed", "cleaning", "Need thorough cleaning of 3-room apartment, including windows, bathrooms and kitchen. Cleaning supplies provided."),
    ("Grocery delivery from Korzinka", "delivery", "Need groceries delivered from Korzinka supermarket on Amir Temur Ave. List will be provided."),
    ("Help moving furniture", "moving", "Moving a 2-room apartment worth of furniture. 3rd floor, no elevator. Truck available."),
    ("Fix leaking faucet", "repair", "Kitchen faucet dripping constantly. Need certified plumber."),
    ("Assemble IKEA wardrobe", "assembly", "Large PAX wardrobe (200x58x236cm). All parts and tools provided."),
    ("Lawn mowing and hedge trimming", "gardening", "Medium-sized garden. Mowing, trimming, leaf removal. Tools available."),
    ("Paint living room walls", "painting", "Living room ~25 sqm. White paint provided. Need to cover old wallpaper."),
    ("Set up home network", "it-help", "Install router, connect 4 devices, set up Wi-Fi extender."),
    ("Night security guard (10pm–6am)", "security", "One-night coverage for private event. Must have valid security license."),
    ("Cook traditional Uzbek plov", "cooking", "Cook plov for 30 guests. Ingredients provided. Wedding event."),
]


class Command(BaseCommand):
    help = "Seed the database with realistic demo data."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=20, help="Number of users to create")
        parser.add_argument("--jobs", type=int, default=50, help="Number of jobs to create")
        parser.add_argument("--reset", action="store_true", help="Delete existing data first")

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("⚠️  Resetting existing seed data..."))
            self._reset()

        with transaction.atomic():
            self.stdout.write("🌱 Seeding database...")
            categories = self._seed_categories()
            employers, workers = self._seed_users(options["users"])
            self._seed_wallets(employers + workers)
            self._seed_jobs(employers, workers, categories, options["jobs"])

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Seed complete!\n"
            f"   Categories : {len(categories)}\n"
            f"   Employers  : {len(employers)}\n"
            f"   Workers    : {len(workers)}\n"
            f"   Jobs       : {options['jobs']}\n\n"
            f"   Admin credentials:\n"
            f"   Phone  : +998901234567 (any role)\n"
            f"   OTP    : 123456 (in dev mode)\n"
        ))

    def _reset(self):
        from apps.jobs.models import Job, JobCategory
        from apps.payments.models import Transaction, Wallet
        from apps.accounts.models import User
        Job.objects.all().delete()
        Transaction.objects.all().delete()
        Wallet.objects.filter(user__is_staff=False).delete()
        User.objects.filter(is_staff=False).delete()
        JobCategory.objects.all().delete()
        self.stdout.write("  Cleared existing data.")

    def _seed_categories(self):
        from apps.jobs.models import JobCategory
        cats = []
        for data in CATEGORIES:
            cat, _ = JobCategory.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "icon": data["icon"],
                    "sort_order": data["sort_order"],
                    "is_active": True,
                },
            )
            cats.append(cat)
        self.stdout.write(f"  ✓ {len(cats)} categories")
        return cats

    def _seed_users(self, count: int):
        from apps.accounts.models import User

        # Ensure superuser exists
        superuser_phone = "+998901234567"
        if not User.objects.filter(phone_number=superuser_phone).exists():
            User.objects.create_superuser(
                phone_number=superuser_phone,
                password="admin123",
                name="Admin User",
            )
            self.stdout.write(f"  ✓ Superuser created: {superuser_phone}")

        half = count // 2
        employers, workers = [], []

        for i in range(half):
            phone = f"+9989{random.randint(10, 99)}{random.randint(1000000, 9999999)}"
            name = random.choice(UZBEK_NAMES)
            user, created = User.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "role": "employer",
                    "name": name,
                    "rating": Decimal(str(round(random.uniform(3.5, 5.0), 1))),
                    "rating_count": random.randint(1, 50),
                    "is_profile_complete": True,
                },
            )
            if created:
                employers.append(user)

        for i in range(half):
            phone = f"+9989{random.randint(10, 99)}{random.randint(1000000, 9999999)}"
            name = random.choice(UZBEK_NAMES)
            user, created = User.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "role": "worker",
                    "name": name,
                    "rating": Decimal(str(round(random.uniform(3.0, 5.0), 1))),
                    "rating_count": random.randint(0, 100),
                    "is_profile_complete": True,
                },
            )
            if created:
                workers.append(user)

        self.stdout.write(f"  ✓ {len(employers)} employers, {len(workers)} workers")
        return employers, workers

    def _seed_wallets(self, users):
        from apps.payments.models import Wallet, Transaction, TransactionType, TransactionStatus
        for user in users:
            wallet, _ = Wallet.objects.get_or_create(user=user)
            if wallet.balance == 0:
                deposit = random.randint(500_000, 10_000_000)  # 5,000–100,000 UZS
                wallet.balance = deposit
                wallet.save(update_fields=["balance"])
                Transaction.objects.create(
                    wallet=wallet,
                    transaction_type=TransactionType.DEPOSIT,
                    direction="credit",
                    amount=deposit,
                    balance_before=0,
                    balance_after=deposit,
                    status=TransactionStatus.COMPLETED,
                    provider="seed",
                    description="Seed deposit",
                )
        self.stdout.write(f"  ✓ {len(users)} wallets funded")

    def _seed_jobs(self, employers, workers, categories, count: int):
        from django.utils import timezone
        from datetime import timedelta
        from apps.jobs.models import Job, JobStatus
        from apps.payments.models import Wallet, Transaction, TransactionType, TransactionStatus

        if not employers or not workers:
            self.stdout.write(self.style.WARNING("  ⚠ No employers or workers — skipping jobs"))
            return

        statuses = [
            JobStatus.CREATED,
            JobStatus.CREATED,
            JobStatus.CREATED,  # Bias toward open jobs
            JobStatus.ACCEPTED,
            JobStatus.IN_PROGRESS,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
        ]

        cat_by_slug = {c.slug: c for c in categories}
        jobs_created = 0

        for _ in range(count):
            template = random.choice(JOB_TEMPLATES)
            title, cat_slug, description = template
            category = cat_by_slug.get(cat_slug, random.choice(categories))
            employer = random.choice(employers)
            loc = random.choice(TASHKENT_LOCATIONS)
            price = random.choice([
                5000, 10000, 15000, 20000, 30000, 50000,
                75000, 100000, 150000, 200000,
            ]) * 100  # tiyin
            status = random.choice(statuses)
            scheduled = timezone.now() + timedelta(hours=random.randint(1, 72))

            # Make sure employer has enough balance (just set it high for seed)
            wallet = Wallet.objects.get(user=employer)
            if wallet.balance < price:
                wallet.balance += price * 2
                wallet.save(update_fields=["balance"])

            job = Job(
                employer=employer,
                title=title + f" #{random.randint(100, 999)}",
                description=description,
                category=category,
                price=price,
                latitude=loc[0] + random.uniform(-0.02, 0.02),
                longitude=loc[1] + random.uniform(-0.02, 0.02),
                address=loc[2],
                status=status,
                scheduled_time=scheduled,
            )

            if status in (
                JobStatus.ACCEPTED, JobStatus.IN_PROGRESS,
                JobStatus.COMPLETED, JobStatus.CANCELLED,
            ):
                worker = random.choice(workers)
                job.worker = worker
                job.accepted_at = timezone.now() - timedelta(hours=random.randint(1, 24))

            if status == JobStatus.IN_PROGRESS:
                job.started_at = timezone.now() - timedelta(hours=random.randint(1, 5))

            if status == JobStatus.COMPLETED:
                job.completed_at = timezone.now() - timedelta(minutes=random.randint(30, 300))

            if status == JobStatus.CANCELLED:
                job.cancelled_at = timezone.now() - timedelta(hours=random.randint(1, 12))
                job.cancel_reason = "Cancelled during seed"
                job.worker = None

            job.save()

            # Escrow transaction for non-cancelled/non-created
            if status != JobStatus.CANCELLED:
                wallet.balance -= price
                wallet.held_balance += price
                wallet.save(update_fields=["balance", "held_balance"])
                Transaction.objects.create(
                    wallet=wallet,
                    transaction_type=TransactionType.JOB_PAYMENT,
                    direction="debit",
                    amount=price,
                    balance_before=wallet.balance + price,
                    balance_after=wallet.balance,
                    status=TransactionStatus.COMPLETED,
                    job=job,
                    provider="internal",
                    description=f"Seed escrow for: {job.title}",
                )

            jobs_created += 1

        self.stdout.write(f"  ✓ {jobs_created} jobs created")
