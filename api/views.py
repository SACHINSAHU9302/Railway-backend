# ============================================================
# IMPORTS
# ============================================================

import json
import logging
import hashlib
import secrets
from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.db.models import Q


from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import RailwayDocument
from .models import UserProfile
from .models import (
    Station,
    Platform,
    Facility,
    Train,
    ActivityLog,
    AdminEmailOTP,
)
from .serializers import RegisterSerializer
from .serializers import PlatformSerializer
from .serializers import FacilitySerializer
from .serializers import RailwayDocumentSerializer
from .serializers import UserManagementSerializer

from rag.chain import ask_rag


logger = logging.getLogger(__name__)
# User Registration API
# User Registration API
# User Registration API

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Generate JWT token pair for the newly registered user
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        return Response(
            {
                "success": True,
                "message": "Account created successfully.",
                "access": str(access),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "date_joined": user.date_joined,
                },
            },
            status=status.HTTP_201_CREATED,
        )

# 1. RAILWAY RULES RAG API
# Endpoint: POST /api/rag/query/


@csrf_exempt
def rag_query(request):
    """
    Railway Rules RAG API.

    Request:
        POST /api/rag/query/

    JSON body:
        {
            "question": "What should I do if my luggage is stolen?"
        }

    Response:
        {
            "success": true,
            "question": "...",
            "answer": "...",
            "sources": [...]
        }
    """

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "error": "Only POST method is allowed.",
            },
            status=405,
        )

    # Parse request JSON
    try:
        data = json.loads(request.body or b"{}")

    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid JSON request body.",
            },
            status=400,
        )

    # Validate JSON object
    if not isinstance(data, dict):
        return JsonResponse(
            {
                "success": False,
                "error": "Request body must be a JSON object.",
            },
            status=400,
        )

    # Validate question
    question = data.get("question", "")

    if not isinstance(question, str) or not question.strip():
        return JsonResponse(
            {
                "success": False,
                "error": "Please provide a valid question.",
            },
            status=400,
        )

    question = question.strip()

    try:
        # Use the same RAG chain tested directly in Python.
        result = ask_rag(question)

        answer = result.get("answer", "")
        sources = result.get("sources", [])

        return JsonResponse(
            {
                "success": True,
                "question": question,
                "answer": answer,
                "sources": sources,
            },
            status=200,
        )

    except Exception:
        # Keep API keys and internal implementation details private.
        logger.exception("Railway RAG query failed.")

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Railway information service is temporarily "
                    "unavailable. Please try again."
                ),
            },
            status=500,
        )


# ============================================================
# ============================================================
# STATION MANAGEMENT - CRUD APIs
# ============================================================
#
# GET    /api/stations/                  -> List all stations
# POST   /api/stations/                  -> Create a station
# GET    /api/stations/<station_id>/     -> Get station details
# PUT    /api/stations/<station_id>/     -> Update a station
# DELETE /api/stations/<station_id>/     -> Delete a station
#
# GET is public. POST, PUT and DELETE require an active staff user.
# Every successful create/update/delete writes an ActivityLog.
# ============================================================


# HELPER: Return the logged-in admin's display name for the activity log.
def get_station_admin_name(request):
    user = request.user
    if user.is_authenticated:
        return user.get_full_name() or user.get_username()
    return "System"


# HELPER: Allow write operations only for active staff/admin users.
def is_station_admin(request):
    user = request.user
    return user.is_authenticated and user.is_active and user.is_staff


# HELPER: Save an activity record. Called inside the same DB transaction
# as the station change, so a failed operation does not leave a false log.
def create_station_activity(request, action, activity_type, description):
    ActivityLog.objects.create(
        action=action,
        performed_by=get_station_admin_name(request),
        activity_type=activity_type,
        description=description,
    )


# API 1: STATION LIST
# GET  -> Return all stations.
# POST -> Validate and create a station; then write an "add" activity.
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def station_list(request):

    # ------------------------- GET -------------------------
    if request.method == "GET":
        stations = Station.objects.all().order_by("station_name")
        results = [
            {
                "id": station.id,
                "station_code": station.station_code,
                "station_name": station.station_name,
                "city": station.city,
                "state": station.state,
                "address": station.address,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "platform_count": station.platform_count,
            }
            for station in stations
        ]
        return Response(
            {
                "success": True,
                "message": "Stations fetched successfully.",
                "count": len(results),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )

    # ------------------------- POST ------------------------
    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data
    station_code = str(data.get("station_code", "")).strip().upper()
    station_name = str(data.get("station_name", "")).strip()
    city = str(data.get("city", "")).strip()
    state_name = str(data.get("state", "")).strip()
    address = str(data.get("address", "") or "").strip()

    # Required field validation.
    if not all([station_code, station_name, city, state_name]):
        return Response(
            {
                "success": False,
                "message": "Station code, station name, city and state are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Prevent duplicate station codes.
    if Station.objects.filter(station_code=station_code).exists():
        return Response(
            {"success": False, "message": "Station code already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate optional coordinates and platform count.
    try:
        raw_latitude = data.get("latitude")
        raw_longitude = data.get("longitude")
        latitude = float(raw_latitude) if raw_latitude not in (None, "") else None
        longitude = float(raw_longitude) if raw_longitude not in (None, "") else None
        platform_count = int(data.get("platform_count", 0) or 0)

        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        if platform_count < 0:
            raise ValueError("Platform count cannot be negative.")
    except (TypeError, ValueError) as error:
        return Response(
            {"success": False, "message": str(error) or "Invalid numeric values."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create station and its activity log atomically.
    try:
        with transaction.atomic():
            station = Station.objects.create(
                station_code=station_code,
                station_name=station_name,
                city=city,
                state=state_name,
                address=address,
                latitude=latitude,
                longitude=longitude,
                platform_count=platform_count,
            )
            create_station_activity(
                request,
                f"New Station {station.station_code} added",
                "add",
                f"{station.station_name} added in {station.city}.",
            )
    except IntegrityError:
        return Response(
            {"success": False, "message": "Station could not be created; check duplicate data."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "success": True,
            "message": "Station created successfully.",
            "station": {
                "id": station.id,
                "station_code": station.station_code,
                "station_name": station.station_name,
                "city": station.city,
                "state": station.state,
                "address": station.address,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "platform_count": station.platform_count,
            },
        },
        status=status.HTTP_201_CREATED,
    )


# API 2: STATION DETAIL
# GET    -> Return station, platforms and facilities.
# PUT    -> Update only the fields supplied by the frontend.
# DELETE -> Delete the station and write a "delete" activity.
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([AllowAny])
def station_detail(request, station_id):

    # First find the requested station.
    try:
        station = Station.objects.get(id=station_id)
    except Station.DoesNotExist:
        return Response(
            {"success": False, "message": "Station not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # ------------------------- GET -------------------------
    if request.method == "GET":
        platforms = station.platforms.all().order_by("platform_number")
        facilities = (
            station.facilities.select_related("platform")
            .all()
            .order_by("facility_name")
        )

        station_data = {
            "id": station.id,
            "station_code": station.station_code,
            "station_name": station.station_name,
            "city": station.city,
            "state": station.state,
            "address": station.address,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "platform_count": station.platform_count,
        }

        platform_data = [
            {
                "id": platform.id,
                "platform_number": platform.platform_number,
                "name": platform.name,
                "accessibility": platform.accessibility,
            }
            for platform in platforms
        ]

        facility_data = [
            {
                "id": facility.id,
                "facility_type": facility.facility_type,
                "facility_name": facility.facility_name,
                "description": facility.description,
                "platform_id": facility.platform_id,
                "platform_number": (
                    facility.platform.platform_number if facility.platform else None
                ),
                "latitude": facility.latitude,
                "longitude": facility.longitude,
                "accessibility": facility.accessibility,
                "contact_info": facility.contact_info,
                "additional_notes": facility.additional_notes,
            }
            for facility in facilities
        ]

        return Response(
            {
                "success": True,
                "station": station_data,
                "platforms": platform_data,
                "facilities": facility_data,
            },
            status=status.HTTP_200_OK,
        )

    # Write methods require an active admin.
    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ------------------------- PUT -------------------------
    if request.method == "PUT":
        data = request.data
        old_station_name = station.station_name

        # Whitelist fields; ignore any unexpected frontend fields.
        allowed_fields = {
            "station_code",
            "station_name",
            "city",
            "state",
            "address",
            "latitude",
            "longitude",
            "platform_count",
        }

        try:
            with transaction.atomic():
                for field in allowed_fields:
                    if field not in data:
                        continue

                    value = data[field]

                    if field == "station_code":
                        value = str(value).strip().upper()
                        if not value:
                            raise ValueError("Station code is required.")
                        duplicate = Station.objects.filter(
                            station_code=value
                        ).exclude(id=station.id).exists()
                        if duplicate:
                            raise ValueError("Station code already exists.")

                    elif field in {"station_name", "city", "state"}:
                        value = str(value).strip()
                        if not value:
                            raise ValueError(f"{field} is required.")

                    elif field == "address":
                        value = str(value or "").strip()

                    elif field == "latitude":
                        value = float(value) if value not in (None, "") else None
                        if value is not None and not -90 <= value <= 90:
                            raise ValueError("Latitude must be between -90 and 90.")

                    elif field == "longitude":
                        value = float(value) if value not in (None, "") else None
                        if value is not None and not -180 <= value <= 180:
                            raise ValueError("Longitude must be between -180 and 180.")

                    elif field == "platform_count":
                        value = int(value)
                        if value < 0:
                            raise ValueError("Platform count cannot be negative.")

                    setattr(station, field, value)

                station.save()

                create_station_activity(
                    request,
                    f"Station {station.station_code} updated",
                    "update",
                    f"Station {old_station_name} updated to {station.station_name}.",
                )

        except (TypeError, ValueError) as error:
            return Response(
                {"success": False, "message": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {"success": False, "message": "Station update failed due to duplicate data."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "message": "Station updated successfully.",
                "station": {
                    "id": station.id,
                    "station_code": station.station_code,
                    "station_name": station.station_name,
                    "city": station.city,
                    "state": station.state,
                    "address": station.address,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "platform_count": station.platform_count,
                },
            },
            status=status.HTTP_200_OK,
        )

    # ------------------------ DELETE -----------------------
    if request.method == "DELETE":
        deleted_name = station.station_name
        deleted_code = station.station_code

        # Log and deletion happen in one transaction.
        with transaction.atomic():
            create_station_activity(
                request,
                f"Station {deleted_code} deleted",
                "delete",
                f"Station {deleted_name} ({deleted_code}) deleted.",
            )
            station.delete()

        return Response(
            {
                "success": True,
                "message": "Station deleted successfully.",
                "deleted_station": {
                    "station_code": deleted_code,
                    "station_name": deleted_name,
                },
            },
            status=status.HTTP_200_OK,
        )


# 4. FACILITY FINDER API
# Endpoint: GET /api/facilities/
# ============================================================

@require_GET
def facility_list(request):
    """
    Find railway facilities.

    Optional query parameters:
        station_id
        type
        search

    Examples:
        /api/facilities/
        /api/facilities/?station_id=1
        /api/facilities/?type=Restroom
        /api/facilities/?search=ticket
        /api/facilities/?station_id=1&type=Restroom
    """

    facilities = Facility.objects.select_related(
        "station",
        "platform",
    ).all().order_by("facility_name")

    station_id = request.GET.get("station_id", "").strip()
    facility_type = request.GET.get("type", "").strip()
    search = request.GET.get("search", "").strip()

    # Filter by station
    if station_id:
        if not station_id.isdigit():
            return JsonResponse(
                {
                    "success": False,
                    "error": "station_id must be a positive integer.",
                },
                status=400,
            )

        facilities = facilities.filter(
            station_id=int(station_id)
        )

    # Filter by facility type
    if facility_type:
        facilities = facilities.filter(
            facility_type__iexact=facility_type
        )

    # Search by facility name, description or type
    if search:
        facilities = facilities.filter(
            Q(facility_name__icontains=search)
            | Q(description__icontains=search)
            | Q(facility_type__icontains=search)
        )

    data = []

    for facility in facilities:
        data.append(
            {
                "id": facility.id,
                "facility_type": facility.facility_type,
                "facility_name": facility.facility_name,
                "description": facility.description,
                "station_id": facility.station_id,
                "station_name": facility.station.station_name,
                "station_code": facility.station.station_code,
                "platform_id": facility.platform_id,
                "platform_number": (
                    facility.platform.platform_number
                    if facility.platform
                    else None
                ),
                "latitude": facility.latitude,
                "longitude": facility.longitude,
                "accessibility": facility.accessibility,
                "contact_info": facility.contact_info,
                "additional_notes": facility.additional_notes,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "count": len(data),
            "results": data,
        }
    )

# RAILWAY DOCUMENTS API
# Endpoint: GET /api/documents/


@require_GET
def document_list(request):
    """
    Return railway documents available in the local knowledge folders.
    """

    base_dir = Path(settings.BASE_DIR)

    document_folders = [
        base_dir / "documents",
        base_dir / "railway_documents",
    ]

    documents = []
    seen = set()

    for folder in document_folders:
        if not folder.exists():
            continue

        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in {".pdf", ".txt", ".html"}:
                continue

            relative_path = file_path.relative_to(base_dir).as_posix()

            if relative_path in seen:
                continue

            seen.add(relative_path)

            documents.append({
                "id": relative_path,
                "title": file_path.stem.replace("_", " ").replace("-", " ").title(),
                "source": relative_path,
                "file_type": file_path.suffix.lower().lstrip("."),
                "category": "Railway Rules & Documents",
            })

    return JsonResponse({
        "success": True,
        "count": len(documents),
        "results": documents,
    })

# ============================================================
# ADMIN EMAIL OTP AUTHENTICATION
# ============================================================

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_send_otp(request):
    email = request.data.get("email", "")

    if not isinstance(email, str) or not email.strip():
        return Response(
            {"success": False, "message": "Valid email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = email.strip().lower()
    User = get_user_model()

    user = User.objects.filter(
        email__iexact=email,
        is_staff=True,
        is_active=True,
    ).first()

    if not user:
        return Response(
            {
                "success": False,
                "message": "If this email belongs to an authorized admin, an OTP will be sent.",
            },
            status=status.HTTP_200_OK,
        )

    cooldown_key = f"admin_otp_cooldown_{user.pk}"

    if cache.get(cooldown_key):
        return Response(
            {
                "success": False,
                "message": "Please wait before requesting another OTP.",
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    AdminEmailOTP.objects.filter(
        user=user,
        is_used=False,
    ).update(is_used=True)

    otp_record = AdminEmailOTP.objects.create(
        user=user,
        otp_hash=otp_hash,
        expires_at=timezone.now() + timedelta(
            minutes=OTP_EXPIRY_MINUTES
        ),
    )

    try:
        send_mail(
            subject="RailVision AI Admin Login OTP",
            message=(
                f"Your RailVision AI login OTP is {otp}.\n\n"
                "This OTP expires in 5 minutes. "
                "Do not share it with anyone."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send admin login OTP.")
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        return Response(
            {
                "success": False,
                "message": "Unable to send OTP. Please try again later.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    cache.set(cooldown_key, True, timeout=OTP_RESEND_SECONDS)

    return Response(
        {
            "success": True,
            "message": "If this email belongs to an authorized admin, an OTP has been sent.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_verify_otp(request):
    email = request.data.get("email", "")
    otp = request.data.get("otp", "")

    if (
        not isinstance(email, str)
        or not email.strip()
        or not isinstance(otp, str)
        or not otp.isdigit()
        or len(otp) != 6
    ):
        return Response(
            {
                "success": False,
                "message": "Valid email and 6-digit OTP are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()

    user = User.objects.filter(
        email__iexact=email.strip(),
        is_staff=True,
        is_active=True,
    ).first()

    if not user:
        return Response(
            {"success": False, "message": "Invalid or expired OTP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_record = AdminEmailOTP.objects.filter(
        user=user,
        is_used=False,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()

    if not otp_record:
        return Response(
            {"success": False, "message": "Invalid or expired OTP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp_record.attempts >= OTP_MAX_ATTEMPTS:
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        return Response(
            {"success": False, "message": "Too many attempts. Request a new OTP."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    submitted_hash = hashlib.sha256(otp.encode()).hexdigest()

    if not secrets.compare_digest(otp_record.otp_hash, submitted_hash):
        otp_record.attempts += 1

        if otp_record.attempts >= OTP_MAX_ATTEMPTS:
            otp_record.is_used = True

        otp_record.save(update_fields=["attempts", "is_used"])

        return Response(
            {"success": False, "message": "Invalid or expired OTP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_record.is_used = True
    otp_record.save(update_fields=["is_used"])

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "success": True,
            "message": "Admin login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.pk,
                "email": user.email,
                "username": user.get_username(),
            },
        },
        status=status.HTTP_200_OK,
    )
    
    

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_profile(request):
    user = request.user

    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_joined": user.date_joined,
    })

# ============================================================
# ADMIN PROFILE API
# Endpoint: GET /api/auth/admin/profile/
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_profile(request):
    user = request.user

    # Allow only active staff/admin users
    if not user.is_active or not user.is_staff:
        return Response(
            {
                "success": False,
                "message": "Admin access required.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(
        {
            "success": True,
            "user": {
                "id": user.id,
                "username": user.get_username(),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
            },
        },
        status=status.HTTP_200_OK,
    )
    # ============================================================
# ADMIN DASHBOARD STATISTICS API
# Endpoint: GET /api/admin/dashboard/
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_dashboard_stats(request):

    # Only active admin users can access this API
    if not request.user.is_active or not request.user.is_staff:
        return Response(
            {
                "success": False,
                "message": "Admin access required."
            },
            status=status.HTTP_403_FORBIDDEN
        )

    stats = {
        "total_stations": Station.objects.count(),
        "total_platforms": Platform.objects.count(),
        "total_facilities": Facility.objects.count(),
        "total_trains": Train.objects.count(),
    }

    return Response(
        {
            "success": True,
            "message": "Dashboard statistics fetched successfully.",
            "stats": stats
        },
        status=status.HTTP_200_OK
    )


# ============================================================
# ADMIN RECENT ACTIVITY API
# Endpoint: GET /api/admin/activities/
# Purpose: Return the latest 10 activity records for the admin dashboard.
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_recent_activities(request):

    # Only active staff/admin users may view admin activity.
    if not request.user.is_active or not request.user.is_staff:
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    activities = ActivityLog.objects.all()[:10]

    results = [
        {
            "id": activity.id,
            "action": activity.action,
            "user": activity.performed_by,
            "type": activity.activity_type,
            "description": activity.description,
            "time": activity.created_at,
        }
        for activity in activities
    ]

    return Response(
        {
            "success": True,
            "count": len(results),
            "results": results,
        },
        status=status.HTTP_200_OK,
    )

# ============================================================
# PLATFORM MANAGEMENT API
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def platform_list(request):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "GET":

        platforms = Platform.objects.select_related(
            "station"
        ).all().order_by("station__station_name", "platform_number")

        serializer = PlatformSerializer(platforms, many=True)

        return Response({
            "success": True,
            "count": platforms.count(),
            "results": serializer.data
        })

    serializer = PlatformSerializer(data=request.data)

    if serializer.is_valid():
        platform = serializer.save()

        create_station_activity(
            request,
            f"Platform {platform.platform_number} added",
            "add",
            f"Platform added at {platform.station.station_name}."
        )

        return Response({
            "success": True,
            "message": "Platform created successfully.",
            "platform": serializer.data
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def platform_detail(request, platform_id):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        platform = Platform.objects.select_related(
            "station"
        ).get(id=platform_id)

    except Platform.DoesNotExist:
        return Response(
            {"success": False, "message": "Platform not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":

        serializer = PlatformSerializer(platform)

        return Response({
            "success": True,
            "platform": serializer.data
        })

    if request.method in ["PUT", "PATCH"]:

        serializer = PlatformSerializer(
            platform,
            data=request.data,
            partial=request.method == "PATCH"
        )

        if serializer.is_valid():
            serializer.save()

            create_station_activity(
                request,
                f"Platform {platform.platform_number} updated",
                "update",
                f"Platform updated at {platform.station.station_name}."
            )

            return Response({
                "success": True,
                "message": "Platform updated successfully.",
                "platform": serializer.data
            })

        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":

        platform_number = platform.platform_number
        station_name = platform.station.station_name

        with transaction.atomic():

            create_station_activity(
                request,
                f"Platform {platform_number} deleted",
                "delete",
                f"Platform deleted from {station_name}."
            )

            platform.delete()

        return Response({
            "success": True,
            "message": "Platform deleted successfully."
        })
        
        # ============================================================
# ADMIN FACILITY MANAGEMENT API
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admin_facility_list(request):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "GET":

        facilities = Facility.objects.select_related(
            "station", "platform"
        ).all().order_by("-created_at")

        station_id = request.query_params.get("station_id")
        facility_type = request.query_params.get("type")
        search = request.query_params.get("search")

        if station_id:
            facilities = facilities.filter(station_id=station_id)

        if facility_type:
            facilities = facilities.filter(facility_type=facility_type)

        if search:
            facilities = facilities.filter(
                Q(facility_name__icontains=search) |
                Q(description__icontains=search) |
                Q(facility_type__icontains=search)
            )

        serializer = FacilitySerializer(facilities, many=True)

        return Response({
            "success": True,
            "count": facilities.count(),
            "results": serializer.data
        })

    serializer = FacilitySerializer(data=request.data)

    if serializer.is_valid():
        facility = serializer.save()

        create_station_activity(
            request,
            f"Facility {facility.facility_name} added",
            "add",
            f"Facility added at {facility.station.station_name}."
        )

        return Response({
            "success": True,
            "message": "Facility created successfully.",
            "facility": serializer.data
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def admin_facility_detail(request, facility_id):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        facility = Facility.objects.select_related(
            "station", "platform"
        ).get(id=facility_id)

    except Facility.DoesNotExist:
        return Response(
            {"success": False, "message": "Facility not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":

        serializer = FacilitySerializer(facility)

        return Response({
            "success": True,
            "facility": serializer.data
        })

    if request.method in ["PUT", "PATCH"]:

        serializer = FacilitySerializer(
            facility,
            data=request.data,
            partial=request.method == "PATCH"
        )

        if serializer.is_valid():
            serializer.save()

            create_station_activity(
                request,
                f"Facility {facility.facility_name} updated",
                "update",
                f"Facility updated at {facility.station.station_name}."
            )

            return Response({
                "success": True,
                "message": "Facility updated successfully.",
                "facility": serializer.data
            })

        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":

        facility_name = facility.facility_name

        with transaction.atomic():

            create_station_activity(
                request,
                f"Facility {facility_name} deleted",
                "delete",
                f"Facility deleted from {facility.station.station_name}."
            )

            facility.delete()

        return Response({
            "success": True,
            "message": "Facility deleted successfully."
        })# ============================================================
# ADMIN DOCUMENT MANAGEMENT API
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admin_document_list(request):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == "GET":

        documents = RailwayDocument.objects.select_related(
            "uploaded_by", "verified_by"
        ).all().order_by("-uploaded_at")

        search = request.query_params.get("search")
        verification_status = request.query_params.get("status")

        if search:
            documents = documents.filter(
                Q(title__icontains=search) |
                Q(original_filename__icontains=search) |
                Q(category__icontains=search)
            )

        if verification_status:
            documents = documents.filter(
                verification_status=verification_status
            )

        serializer = RailwayDocumentSerializer(
            documents,
            many=True,
            context={"request": request}
        )

        return Response({
            "success": True,
            "count": documents.count(),
            "results": serializer.data
        })

    serializer = RailwayDocumentSerializer(
        data=request.data,
        context={"request": request}
    )

    if serializer.is_valid():
        document = serializer.save(uploaded_by=request.user)

        create_station_activity(
            request,
            f"Document {document.title} uploaded",
            "upload",
            "Railway document uploaded for verification."
        )

        return Response({
            "success": True,
            "message": "Document uploaded successfully.",
            "document": RailwayDocumentSerializer(document).data
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# DOCUMENT DETAIL / DELETE
# ============================================================

@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def admin_document_detail(request, document_id):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        document = RailwayDocument.objects.get(id=document_id)
    except RailwayDocument.DoesNotExist:
        return Response(
            {"success": False, "message": "Document not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = RailwayDocumentSerializer(document)

        return Response({
            "success": True,
            "document": serializer.data
        })

    title = document.title

    with transaction.atomic():
        create_station_activity(
            request,
            f"Document {title} deleted",
            "delete",
            "Railway document deleted."
        )

        document.delete()

    return Response({
        "success": True,
        "message": "Document deleted successfully."
    })


# ============================================================
# DOCUMENT APPROVE / REJECT
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_railway_document(request, document_id):

    if not is_station_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        document = RailwayDocument.objects.get(id=document_id)
    except RailwayDocument.DoesNotExist:
        return Response(
            {"success": False, "message": "Document not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    decision = request.data.get("status")
    remarks = request.data.get("remarks", "")

    if decision not in ["Approved", "Rejected"]:
        return Response(
            {
                "success": False,
                "message": "Status must be Approved or Rejected."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    document.verification_status = decision
    document.verification_remarks = remarks
    document.verified_by = request.user
    document.verified_at = timezone.now()

    document.save(update_fields=[
        "verification_status",
        "verification_remarks",
        "verified_by",
        "verified_at"
    ])

    create_station_activity(
        request,
        f"Document {document.title} {decision}",
        "verify",
        f"Document verification status changed to {decision}."
    )

    return Response({
        "success": True,
        "message": f"Document {decision.lower()} successfully.",
        "document": RailwayDocumentSerializer(document).data
    })
    
    # ============================================================
# USER MANAGEMENT APIs
# ============================================================

def is_user_management_admin(request):
    return (
        request.user.is_authenticated
        and request.user.is_active
        and request.user.is_staff
    )


# GET /api/users/
# List users with search, filters and pagination.

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_list(request):

    if not is_user_management_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    users = get_user_model().objects.select_related(
        "profile"
    ).all().order_by("-date_joined")

    search = request.query_params.get("search", "").strip()
    role = request.query_params.get("role", "").strip()
    user_status = request.query_params.get("status", "").strip()

    if search:
        users = users.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(profile__phone__icontains=search)
        )

    if role:
        users = users.filter(profile__role=role)

    if user_status:
        users = users.filter(profile__status=user_status)

    paginator = Paginator(users, 10)

    page_number = request.query_params.get("page", 1)
    page = paginator.get_page(page_number)

    serializer = UserManagementSerializer(
        page.object_list,
        many=True
    )

    return Response({
        "success": True,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page.number,
        "results": serializer.data
    })


# GET /api/users/<id>/
# PATCH /api/users/<id>/
# DELETE /api/users/<id>/

@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def user_detail(request, user_id):

    if not is_user_management_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    User = get_user_model()

    try:
        user = User.objects.select_related("profile").get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = UserManagementSerializer(user)

        return Response({
            "success": True,
            "user": serializer.data
        })

    if request.method == "PATCH":

        if user.pk == request.user.pk:
            return Response(
                {
                    "success": False,
                    "message": "You cannot modify your own account here."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserManagementSerializer(
            user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()

            return Response({
                "success": True,
                "message": "User updated successfully.",
                "user": serializer.data
            })

        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":

        if user.pk == request.user.pk:
            return Response(
                {
                    "success": False,
                    "message": "You cannot delete your own account."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user.delete()

        return Response({
            "success": True,
            "message": "User deleted successfully."
        })


# PATCH /api/users/<id>/status/

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def user_status_update(request, user_id):

    if not is_user_management_admin(request):
        return Response(
            {"success": False, "message": "Admin access required."},
            status=status.HTTP_403_FORBIDDEN
        )

    User = get_user_model()

    try:
        user = User.objects.select_related("profile").get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if user.pk == request.user.pk:
        return Response(
            {
                "success": False,
                "message": "You cannot change your own status."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    new_status = request.data.get("status")

    if new_status not in ["Active", "Inactive", "Blocked"]:
        return Response(
            {"success": False, "message": "Invalid user status."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.profile.status = new_status

    # Blocked and Inactive users cannot log in.
    user.is_active = new_status == "Active"

    user.profile.save()
    user.save(update_fields=["is_active"])

    return Response({
        "success": True,
        "message": f"User status changed to {new_status}.",
        "status": new_status
    })