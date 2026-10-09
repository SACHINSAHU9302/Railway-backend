from django.db import models


class Station(models.Model):

    station_code = models.CharField(
        max_length=20,
        unique=True
    )

    station_name = models.CharField(
        max_length=200
    )

    city = models.CharField(
        max_length=100,
        blank=True
    )

    state = models.CharField(
        max_length=100,
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    platform_count = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):

        return (
            f"{self.station_name} "
            f"({self.station_code})"
        )


class Platform(models.Model):

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="platforms"
    )

    platform_number = models.PositiveIntegerField()

    name = models.CharField(
        max_length=100,
        blank=True
    )

    accessibility = models.BooleanField(
        default=False
    )

    def __str__(self):

        return (
            f"{self.station.station_name} "
            f"- Platform {self.platform_number}"
        )


class Facility(models.Model):

    FACILITY_TYPES = [

        ("ticket_counter", "Ticket Counter"),

        ("waiting_room", "Waiting Room"),

        ("restroom", "Restroom"),

        ("food_court", "Food Court"),

        ("parking", "Parking"),

        ("rpf", "RPF Support"),

        ("medical", "Medical Assistance"),

        ("atm", "ATM"),

        ("water", "Drinking Water"),

        ("lift", "Lift"),

        ("escalator", "Escalator"),

        ("foot_over_bridge", "Foot Over Bridge"),

        ("other", "Other"),
    ]

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="facilities"
    )

    platform = models.ForeignKey(
        Platform,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facilities"
    )

    facility_type = models.CharField(
        max_length=50,
        choices=FACILITY_TYPES
    )

    facility_name = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True
    )

    latitude = models.FloatField(
        null=True,
        blank=True
    )

    longitude = models.FloatField(
        null=True,
        blank=True
    )

    accessibility = models.BooleanField(
        default=False
    )

    contact_info = models.CharField(
        max_length=200,
        blank=True
    )

    additional_notes = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return (
            f"{self.facility_name} - "
            f"{self.station.station_name}"
        )


class Train(models.Model):

    train_number = models.CharField(
        max_length=20,
        unique=True
    )

    train_name = models.CharField(
        max_length=200
    )

    source = models.CharField(
        max_length=200
    )

    destination = models.CharField(
        max_length=200
    )

    train_type = models.CharField(
        max_length=100,
        blank=True
    )

    active = models.BooleanField(
        default=True
    )

    def __str__(self):

        return (
            f"{self.train_number} - "
            f"{self.train_name}"
        )