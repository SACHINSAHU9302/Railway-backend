from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Station,
    Platform,
    Facility,
    RailwayDocument,
    ActivityLog,
    UserProfile, 
    )

User = get_user_model()


# ============================================================
# USER REGISTRATION SERIALIZER
# ============================================================

class RegisterSerializer(serializers.ModelSerializer):

    name = serializers.CharField(write_only=True, max_length=150)

    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )

    password2 = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "username",
            "email",
            "password",
            "password2",
        )
        read_only_fields = ("id",)

        extra_kwargs = {
            "username": {"required": False},
            "email": {"required": True},
        }

    def validate_email(self, value):
        email = value.strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({
                "password2": "Passwords do not match."
            })

        return attrs

    def create(self, validated_data):
        name = validated_data.pop("name").strip()
        validated_data.pop("password2")
        password = validated_data.pop("password")

        username = validated_data.pop("username", None)

        if not username:
            username = validated_data["email"].split("@")[0]

        base_username = username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=validated_data["email"],
            first_name=name,
        )

        user.set_password(password)
        user.save()

        return user


# ============================================================
# EMAIL LOGIN SERIALIZER
# ============================================================

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                "detail": "Invalid email or password."
            })

        authenticated_user = authenticate(
            request=self.context.get("request"),
            username=user.username,
            password=password,
        )

        if not authenticated_user or not authenticated_user.is_active:
            raise serializers.ValidationError({
                "detail": "Invalid email or password."
            })

        refresh = self.get_token(authenticated_user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


# ============================================================
# STATION SERIALIZER
# ============================================================

class StationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Station
        fields = "__all__"

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )


# ============================================================
# PLATFORM SERIALIZER
# ============================================================

class PlatformSerializer(serializers.ModelSerializer):

    station_name = serializers.CharField(
        source="station.station_name",
        read_only=True
    )

    station_code = serializers.CharField(
        source="station.station_code",
        read_only=True
    )

    class Meta:
        model = Platform
        fields = "__all__"

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "station_name",
            "station_code",
        )

    def validate(self, attrs):
        station = attrs.get(
            "station",
            getattr(self.instance, "station", None)
        )

        platform_number = attrs.get(
            "platform_number",
            getattr(self.instance, "platform_number", None)
        )

        if station and platform_number:
            existing = Platform.objects.filter(
                station=station,
                platform_number=platform_number
            )

            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise serializers.ValidationError({
                    "platform_number": (
                        "This platform number already exists at this station."
                    )
                })

        return attrs


# ============================================================
# FACILITY SERIALIZER
# ============================================================

class FacilitySerializer(serializers.ModelSerializer):

    station_name = serializers.CharField(
        source="station.station_name",
        read_only=True
    )

    station_code = serializers.CharField(
        source="station.station_code",
        read_only=True
    )

    platform_number = serializers.IntegerField(
        source="platform.platform_number",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Facility
        fields = "__all__"

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "last_verified",
            "station_name",
            "station_code",
            "platform_number",
        )

    def validate(self, attrs):
        station = attrs.get(
            "station",
            getattr(self.instance, "station", None)
        )

        platform = attrs.get(
            "platform",
            getattr(self.instance, "platform", None)
        )

        if platform and station and platform.station_id != station.id:
            raise serializers.ValidationError({
                "platform": "Selected platform does not belong to this station."
            })

        return attrs


# ============================================================
# RAILWAY DOCUMENT SERIALIZER
# ============================================================

class RailwayDocumentSerializer(serializers.ModelSerializer):

    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username",
        read_only=True
    )

    verified_by_name = serializers.CharField(
        source="verified_by.username",
        read_only=True
    )

    class Meta:
        model = RailwayDocument

        fields = "__all__"

        read_only_fields = (
            "id",
            "uploaded_by",
            "verified_by",
            "uploaded_at",
            "verified_at",
            "verification_status",
            "verification_remarks",
            "processing_status",
            "processing_error",
            "is_indexed",
            "original_filename",
            "file_type",
        )

    def validate_file(self, value):
        allowed_extensions = {".pdf", ".txt"}

        filename = value.name.lower()

        import os

        extension = os.path.splitext(filename)[1]

        if extension not in allowed_extensions:
            raise serializers.ValidationError(
                "Only PDF and TXT files are allowed."
            )

        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "File size cannot exceed 10 MB."
            )

        return value

    def create(self, validated_data):
        uploaded_file = validated_data["file"]

        validated_data["original_filename"] = uploaded_file.name

        validated_data["file_type"] = (
            uploaded_file.name.rsplit(".", 1)[-1].lower()
        )

        return super().create(validated_data)


# ============================================================
# ACTIVITY LOG SERIALIZER
# ============================================================

class ActivityLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = ActivityLog
        fields = "__all__"

        read_only_fields = (
            "id",
            "created_at",
        )
        
        # ============================================================
# USER PROFILE SERIALIZER
# ============================================================

class UserProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserProfile
        fields = [
            "phone",
            "role",
            "status",
            "location",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "created_at",
            "updated_at",
        ]


# ============================================================
# USER MANAGEMENT SERIALIZER
# ============================================================

class UserManagementSerializer(serializers.ModelSerializer):

    name = serializers.SerializerMethodField()

    phone = serializers.CharField(
        source="profile.phone",
        required=False,
        allow_blank=True
    )

    role = serializers.CharField(
        source="profile.role",
        required=False
    )

    status = serializers.CharField(
        source="profile.status",
        required=False
    )

    location = serializers.CharField(
        source="profile.location",
        required=False,
        allow_blank=True
    )

    registrationDate = serializers.DateTimeField(
        source="date_joined",
        read_only=True
    )

    lastLogin = serializers.DateTimeField(
        source="last_login",
        read_only=True,
        allow_null=True
    )

    totalComplaints = serializers.IntegerField(
        read_only=True,
        default=0
    )

    class Meta:
        model = User

        fields = [
            "id",
            "name",
            "email",
            "phone",
            "role",
            "status",
            "location",
            "registrationDate",
            "lastLogin",
            "totalComplaints",
        ]

        read_only_fields = [
            "id",
            "registrationDate",
            "lastLogin",
            "totalComplaints",
        ]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username