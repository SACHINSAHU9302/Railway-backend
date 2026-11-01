from django.db import models
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


# ============================================================
# STATION MODEL
# ============================================================

class Station(models.Model):

    station_code = models.CharField(max_length=20, unique=True)
    station_name = models.CharField(max_length=200)

    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)

    # Optional coordinates
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    platform_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.station_name} ({self.station_code})"


# ============================================================
# PLATFORM MODEL
# ============================================================

class Platform(models.Model):

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="platforms"
    )

    platform_number = models.PositiveIntegerField()
    name = models.CharField(max_length=100, blank=True)

    # Existing field preserved
    accessibility = models.BooleanField(default=False)

    # Location
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Platform amenities
    shelter = models.BooleanField(default=False)
    bench = models.BooleanField(default=False)
    drinking_water = models.BooleanField(default=False)
    toilet = models.BooleanField(default=False)

    # Accessibility facilities
    fob_access = models.BooleanField(default=False)
    lift_access = models.BooleanField(default=False)
    escalator_access = models.BooleanField(default=False)
    wheelchair_access = models.BooleanField(default=False)

    # Verification
    VERIFICATION_STATUS = [
        ("Pending", "Pending"),
        ("Verified", "Verified"),
        ("Rejected", "Rejected"),
    ]

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS,
        default="Pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["station", "platform_number"],
                name="unique_platform_per_station"
            )
        ]

    def __str__(self):
        return f"{self.station.station_name} - Platform {self.platform_number}"


# ============================================================
# FACILITY MODEL
# ============================================================

class Facility(models.Model):

    FACILITY_TYPES = [
        ("Ticket Counter", "Ticket Counter"),
        ("Waiting Room", "Waiting Room"),
        ("AC Waiting Room", "AC Waiting Room"),
        ("Toilet", "Toilet"),
        ("Accessible Toilet", "Accessible Toilet"),
        ("Drinking Water", "Drinking Water"),
        ("Food", "Food"),
        ("Restaurant", "Restaurant"),
        ("ATM", "ATM"),
        ("Parking", "Parking"),
        ("Medical", "Medical"),
        ("First Aid", "First Aid"),
        ("RPF", "RPF"),
        ("GRP", "GRP"),
        ("Help Desk", "Help Desk"),
        ("Wheelchair", "Wheelchair"),
        ("Lift", "Lift"),
        ("Escalator", "Escalator"),
        ("FOB", "FOB"),
        ("Stairs", "Stairs"),
        ("Ramp", "Ramp"),
        ("Footway", "Footway"),
        ("Entry", "Entry"),
        ("Exit", "Exit"),
        ("Wi-Fi", "Wi-Fi"),
        ("Charging Point", "Charging Point"),
        ("Other", "Other"),
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

    facility_name = models.CharField(max_length=200)

    description = models.TextField(blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Existing field preserved for compatibility
    accessibility = models.BooleanField(default=False)

    # Detailed accessibility
    accessibility_status = models.CharField(
        max_length=30,
        default="Not Accessible"
    )

    contact_info = models.CharField(max_length=200, blank=True)
    additional_notes = models.TextField(blank=True)

    # Frontend facility fields
    location = models.CharField(max_length=255, blank=True)

    availability = models.CharField(
        max_length=30,
        default="Available"
    )

    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)

    source = models.CharField(max_length=255, blank=True)

    VERIFICATION_STATUS = [
        ("Pending", "Pending"),
        ("Verified", "Verified"),
        ("Rejected", "Rejected"),
    ]

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS,
        default="Pending"
    )

    last_verified = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.facility_name} - {self.station.station_name}"


# ============================================================
# TRAIN MODEL
# ============================================================

class Train(models.Model):

    train_number = models.CharField(max_length=20, unique=True)
    train_name = models.CharField(max_length=200)

    source = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)

    train_type = models.CharField(max_length=100, blank=True)

    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.train_number} - {self.train_name}"


# ============================================================
# ADMIN EMAIL OTP MODEL
# ============================================================

class AdminEmailOTP(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_email_otps"
    )

    otp_hash = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    is_used = models.BooleanField(default=False)

    attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Admin OTP for {self.user.email}"


# ============================================================
# DOCUMENT MANAGEMENT MODEL
# ============================================================

class RailwayDocument(models.Model):

    DOCUMENT_STATUS = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    PROCESSING_STATUS = [
        ("Pending", "Pending"),
        ("Processing", "Processing"),
        ("Completed", "Completed"),
        ("Failed", "Failed"),
    ]

    title = models.CharField(max_length=255)

    description = models.TextField(blank=True)

    category = models.CharField(
        max_length=100,
        blank=True
    )

    file = models.FileField(
        upload_to="railway_documents/%Y/%m/"
    )

    original_filename = models.CharField(
        max_length=255,
        blank=True
    )

    file_type = models.CharField(
        max_length=20,
        blank=True
    )

    verification_status = models.CharField(
        max_length=20,
        choices=DOCUMENT_STATUS,
        default="Pending"
    )

    verification_remarks = models.TextField(blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_railway_documents"
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_railway_documents"
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    verified_at = models.DateTimeField(null=True, blank=True)

    # RAG processing status
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS,
        default="Pending"
    )

    processing_error = models.TextField(blank=True)

    is_indexed = models.BooleanField(default=False)

    def __str__(self):
        return self.title


# ============================================================
# ACTIVITY LOG MODEL
# ============================================================

class ActivityLog(models.Model):

    ACTIVITY_TYPES = [
        ("add", "Add"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("upload", "Upload"),
        ("alert", "Alert"),
        ("verify", "Verify"),
    ]

    action = models.CharField(max_length=255)

    performed_by = models.CharField(
        max_length=150,
        default="System"
    )

    activity_type = models.CharField(
        max_length=20,
        choices=ACTIVITY_TYPES,
        default="add"
    )

    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        return self.action
    
    
    # ============================================================
# USER PROFILE MODEL
# ============================================================

class UserProfile(models.Model):

    ROLE_CHOICES = [
        ("Passenger", "Passenger"),
        ("Admin", "Admin"),
        ("Station Manager", "Station Manager"),
        ("Support Agent", "Support Agent"),
    ]

    STATUS_CHOICES = [
        ("Active", "Active"),
        ("Inactive", "Inactive"),
        ("Blocked", "Blocked"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    phone = models.CharField(
        max_length=15,
        blank=True
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="Passenger"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Active"
    )

    location = models.CharField(
        max_length=255,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"