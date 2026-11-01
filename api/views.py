# IMPORTS
import json
import re
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
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
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
from .models import Station, Platform, Facility
from io import BytesIO
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)
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
    question = data.get("question") or data.get("query", "")

    print("QUESTION:", question)

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


MAX_TICKET_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ============================================================
# 1. HEALTH CHECK
# GET /api/ticket/health/
# ============================================================
@require_GET
def ticket_scanner_health(request):
    return JsonResponse({
        "success": True,
        "service": "RailVision AI Ticket Scanner",
        "status": "online",
    })


# ============================================================
# 2. FIELD AND STATION HELPERS
# ============================================================
def get_ticket_field(text, label):
    """Read either 'Label: value' or a label followed by its value."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    label_pattern = re.compile(
        rf"^{re.escape(label)}\s*:?\s*(.*?)\s*$", re.IGNORECASE
    )

    known_labels = {
        "pnr", "pnr number", "pnr no", "train number", "train name",
        "journey date", "from", "to", "boarding station", "departure",
        "arrival", "class", "quota", "platform", "booking status",
        "passenger details", "passenger name", "age", "gender", "coach",
        "berth", "status", "test notes",
    }

    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if value:
            return value
        if index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            if next_line.lower() not in known_labels:
                return next_line
    return ""


def parse_station(value):
    """Convert 'BHOPAL JN (BPL)' into ('BHOPAL JN', 'BPL')."""
    if not value:
        return "", ""
    match = re.match(r"^(.*?)\s*\(([A-Z0-9]{2,5})\)\s*$", value.strip(), re.I)
    if match:
        return match.group(1).strip(), match.group(2).upper()
    return value.strip(), ""


# ============================================================
# 3. PASSENGER PARSER
# Supports the line-based sample PDF layout shown in testing.
# ============================================================
def _normalize_berth(value):
    value = re.sub(r"[()]", "", value or "").strip().title()
    aliases = {
        "Sl": "Side Lower", "Su": "Side Upper",
        "Side- Lower": "Side Lower", "Side- Upper": "Side Upper",
    }
    value = aliases.get(value, value)
    allowed = {
        "Lower", "Middle", "Upper", "Side Lower", "Side Upper", "Window Seat"
    }
    return value if value in allowed else ""


def _normalize_status(value):
    value = (value or "").upper()
    if re.search(r"\bRAC\b", value):
        return "RAC"
    if re.search(r"\b(WL|WAITLIST|WAITING)\b", value):
        return "WL"
    if re.search(r"\b(CNF|CONFIRMED)\b", value):
        return "CNF"
    return ""


def parse_passengers(text):
    """Parse passenger rows from the project's line-based sample ticket."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    passengers = []

    try:
        section_index = next(
            (i for i, line in enumerate(lines)
             if line.casefold() == "passenger details"),
            -1,
        )
        if section_index < 0:
            return passengers

        # Find the table's Status heading, then read values after it.
        status_header = next(
            (i for i in range(section_index + 1, len(lines))
             if lines[i].casefold() == "status"),
            -1,
        )
        if status_header < 0:
            return passengers

        values = lines[status_header + 1:]
        # Expected sample layout: name, age, gender, coach, berth, status.
        if len(values) < 6:
            return passengers

        name = values[0]
        if name.casefold() in {"test notes", "journey information"}:
            return passengers

        age_match = re.search(r"\b(\d{1,3})\b", values[1])
        age = int(age_match.group(1)) if age_match else 0
        gender_raw = values[2].strip().upper()
        gender = gender_raw if gender_raw in {"M", "F", "O"} else "O"

        coach = values[3].strip()
        if not re.fullmatch(r"[A-Z0-9-]{1,10}", coach, re.I):
            coach = ""

        # Handle both '21 (LOWER)' and separate '21' / '(LOWER)' lines.
        berth_line = values[4]
        berth_match = re.match(
            r"^\s*(\d{1,4})(?:\s*\(([^)]+)\)|\s+([A-Za-z ]+))?\s*$",
            berth_line,
            re.I,
        )
        berth_number = ""
        berth_type = ""
        status_offset = 5

        if berth_match:
            berth_number = berth_match.group(1)
            berth_type = _normalize_berth(berth_match.group(2) or berth_match.group(3) or "")
        elif re.fullmatch(r"\d{1,4}", berth_line):
            berth_number = berth_line
            if len(values) > 6:
                berth_type = _normalize_berth(values[5])
                status_offset = 6

        passenger_status = _normalize_status(
            values[status_offset] if len(values) > status_offset else ""
        )

        if name and not name.isdigit():
            passengers.append({
                "name": name,
                "age": age,
                "gender": gender,
                "coach": coach,
                "berthNumber": berth_number,
                "berthType": berth_type,
                "status": passenger_status,
            })

    except Exception:
        logger.exception("Passenger parsing failed")

    return passengers


# ============================================================
# 4. STRUCTURED TICKET PARSER
# ============================================================
def parse_railway_ticket(extracted_text):
    pnr_match = re.search(r"(?<!\d)\d{10}(?!\d)", extracted_text)
    pnr_number = pnr_match.group(0) if pnr_match else ""

    train_number = get_ticket_field(extracted_text, "Train Number")
    train_name = get_ticket_field(extracted_text, "Train Name")
    journey_date = get_ticket_field(extracted_text, "Journey Date")

    from_value = get_ticket_field(extracted_text, "From")
    to_value = get_ticket_field(extracted_text, "To")
    from_station, from_code = parse_station(from_value)
    to_station, to_code = parse_station(to_value)

    boarding_station = get_ticket_field(extracted_text, "Boarding Station")
    departure_time = get_ticket_field(extracted_text, "Departure")
    arrival_time = get_ticket_field(extracted_text, "Arrival")
    travel_class = get_ticket_field(extracted_text, "Class")
    quota = get_ticket_field(extracted_text, "Quota")

    platform_value = get_ticket_field(extracted_text, "Platform")
    platform_match = re.search(r"\b\d+\b", platform_value)
    platform = int(platform_match.group(0)) if platform_match else None

    passengers = parse_passengers(extracted_text)
    first_passenger = passengers[0] if passengers else {}

    passenger_status = get_ticket_field(extracted_text, "Booking Status")
    if not passenger_status:
        passenger_status = first_passenger.get("status", "")

    # This is a field-completeness ratio, not an ML/OCR confidence score.
    required_fields = [pnr_number, train_number, train_name, journey_date,
                       from_station, to_station]
    completeness_score = round(sum(bool(v) for v in required_fields) / len(required_fields), 2)

    return {
        "pnrNumber": pnr_number,
        "trainNumber": train_number,
        "trainName": train_name,
        "fromStation": from_station,
        "fromStationCode": from_code,
        "toStation": to_station,
        "toStationCode": to_code,
        "boardingStation": boarding_station,
        "journeyDate": journey_date,
        "departureTime": departure_time,
        "arrivalTime": arrival_time,
        "travelClass": travel_class,
        "quota": quota,
        "platform": platform,
        "passengerName": first_passenger.get("name", ""),
        "coach": first_passenger.get("coach", ""),
        "berth": first_passenger.get("berthNumber", ""),
        "berthType": first_passenger.get("berthType", ""),
        "status": passenger_status,
        "passengers": passengers,
        "confidenceScore": completeness_score,
    }


# ============================================================
# 5. PDF EXTRACTION API
# POST /api/ticket/extract/
# ============================================================
@csrf_exempt
def extract_ticket(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Only POST requests are allowed."}, status=405)

    uploaded_file = request.FILES.get("ticketFile")
    if uploaded_file is None:
        return JsonResponse({"success": False, "error": "Upload a file using the ticketFile field."}, status=400)
    if uploaded_file.size == 0:
        return JsonResponse({"success": False, "error": "The uploaded file is empty."}, status=400)
    if uploaded_file.size > MAX_TICKET_FILE_SIZE:
        return JsonResponse({"success": False, "error": "Maximum file size is 10 MB."}, status=400)

    filename = uploaded_file.name.lower()
    if not filename.endswith((".pdf", ".jpg", ".jpeg", ".png")):
        return JsonResponse({"success": False, "error": "Only PDF, JPG and PNG files are supported."}, status=400)

    uploaded_file.seek(0)
    file_header = uploaded_file.read(8)
    uploaded_file.seek(0)

    if filename.endswith(".pdf") and not file_header.startswith(b"%PDF-"):
        return JsonResponse({"success": False, "error": "The uploaded file is not a valid PDF."}, status=400)
    if filename.endswith((".jpg", ".jpeg")) and not file_header.startswith(b"\xff\xd8\xff"):
        return JsonResponse({"success": False, "error": "The uploaded file is not a valid JPEG image."}, status=400)
    if filename.endswith(".png") and not file_header.startswith(b"\x89PNG\r\n\x1a\n"):
        return JsonResponse({"success": False, "error": "The uploaded file is not a valid PNG image."}, status=400)

    # Image files are validated but OCR is not implemented in this endpoint.
    if not filename.endswith(".pdf"):
        return JsonResponse({
            "success": False,
            "error": "Image OCR is not configured. Upload a text-based PDF for now.",
        }, status=501)

    try:
        reader = PdfReader(BytesIO(uploaded_file.read()))
        if reader.is_encrypted:
            return JsonResponse({"success": False, "error": "Password-protected PDFs are not supported."}, status=400)
        if len(reader.pages) > 50:
            return JsonResponse({"success": False, "error": "PDFs with more than 50 pages are not supported."}, status=400)
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.exception("Ticket PDF extraction failed")
        return JsonResponse({"success": False, "error": "Could not read this PDF."}, status=400)

    if not extracted_text.strip():
        return JsonResponse({
            "success": False,
            "error": "No selectable text found. OCR is required for this scanned PDF.",
        }, status=400)

    try:
        ticket_data = parse_railway_ticket(extracted_text)
    except Exception:
        logger.exception("Ticket parsing failed")
        return JsonResponse({"success": False, "error": "Could not parse ticket information."}, status=500)

    return JsonResponse({
        "success": True,
        "message": "PDF text extracted. Please verify the extracted ticket details.",
        "data": {
            "filename": uploaded_file.name,
            "source": "pdf_text_extraction",
            "text_extracted": True,
            "pnr_found": bool(ticket_data["pnrNumber"]),
            "rawTextPreview": extracted_text[:5000],
            **ticket_data,
        },
    }, status=200)


# ============================================================
# 6. MANUAL PNR FORMAT VALIDATION
# POST /api/ticket/pnr/
# NOTE: This does NOT fetch live PNR/booking status.
# ============================================================
@csrf_exempt
def validate_ticket_pnr(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Only POST requests are allowed."}, status=405)

    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid JSON request."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"success": False, "error": "Request body must be a JSON object."}, status=400)

    pnr = str(data.get("pnr", "")).strip()
    if not re.fullmatch(r"\d{10}", pnr):
        return JsonResponse({"success": False, "error": "PNR must contain exactly 10 digits."}, status=400)

    return JsonResponse({
        "success": True,
        "message": "PNR format is valid. Live railway lookup has not been configured.",
        "data": {
            "pnrNumber": pnr,
            "format_valid": True,
            "lookup_available": False,
        },
    }, status=200)

# ============================================================
# USER / ADMIN / PLATFORM / FACILITY / DOCUMENT MANAGEMENT APIs
# Added to preserve the existing RAG, Station and Ticket APIs.
# ============================================================

def _ensure_user_profile(user):
    """Create a default profile for users registered before profile support."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _is_admin_user(user):
    """Central admin permission check."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        return user.profile.role == "Admin" and user.profile.status == "Active"
    except UserProfile.DoesNotExist:
        return False


def _admin_denied():
    return Response(
        {"success": False, "message": "Admin access required."},
        status=status.HTTP_403_FORBIDDEN,
    )


# ------------------------- USER PROFILE -------------------------

@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def user_profile(request):
    from .serializers import UserProfileSerializer

    profile = _ensure_user_profile(request.user)

    if request.method == "GET":
        return Response({
            "success": True,
            "user": {
                "id": request.user.id,
                "username": request.user.username,
                "name": request.user.get_full_name() or request.user.username,
                "email": request.user.email,
            },
            "profile": UserProfileSerializer(profile).data,
        })

    serializer = UserProfileSerializer(
        profile, data=request.data, partial=(request.method == "PATCH")
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({
        "success": True,
        "message": "Profile updated successfully.",
        "profile": serializer.data,
    })


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def admin_profile(request):
    from .serializers import UserProfileSerializer

    if not _is_admin_user(request.user):
        return _admin_denied()

    profile = _ensure_user_profile(request.user)

    if request.method == "GET":
        return Response({
            "success": True,
            "user": {
                "id": request.user.id,
                "username": request.user.username,
                "name": request.user.get_full_name() or request.user.username,
                "email": request.user.email,
                "is_staff": request.user.is_staff,
            },
            "profile": UserProfileSerializer(profile).data,
        })

    serializer = UserProfileSerializer(
        profile, data=request.data, partial=(request.method == "PATCH")
    )
    serializer.is_valid(raise_exception=True)
    # Do not allow an admin to demote their own role through this endpoint.
    if serializer.validated_data.get("role", profile.role) != "Admin":
        return Response(
            {"success": False, "message": "Admin role cannot be changed here."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer.save()
    return Response({
        "success": True,
        "message": "Admin profile updated successfully.",
        "profile": serializer.data,
    })


# ------------------------- USER MANAGEMENT -------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_list(request):
    if not _is_admin_user(request.user):
        return _admin_denied()

    users = get_user_model().objects.all().order_by("-date_joined")
    search = request.query_params.get("search", "").strip()
    if search:
        users = users.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    for user in users:
        _ensure_user_profile(user)

    page_number = request.query_params.get("page", "1")
    page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
    paginator = Paginator(users, page_size)
    page = paginator.get_page(page_number)

    serializer = UserManagementSerializer(page.object_list, many=True)
    return Response({
        "success": True,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page.number,
        "results": serializer.data,
    })


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def user_detail(request, user_id):
    if not _is_admin_user(request.user):
        return _admin_denied()

    User = get_user_model()
    try:
        target_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile = _ensure_user_profile(target_user)

    if request.method == "GET":
        return Response({
            "success": True,
            "user": UserManagementSerializer(target_user).data,
        })

    data = request.data
    allowed_user_fields = {"first_name", "last_name", "email"}
    for field in allowed_user_fields:
        if field in data:
            value = str(data[field]).strip()
            if field == "email":
                if not value or User.objects.filter(
                    email__iexact=value
                ).exclude(pk=target_user.pk).exists():
                    return Response(
                        {"success": False, "message": "Email is invalid or already used."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                value = value.lower()
            setattr(target_user, field, value)
    target_user.save()

    profile_data = {
        key: data[key]
        for key in ("phone", "role", "status", "location")
        if key in data
    }
    if profile_data:
        from .serializers import UserProfileSerializer
        profile_serializer = UserProfileSerializer(
            profile, data=profile_data, partial=True
        )
        profile_serializer.is_valid(raise_exception=True)
        profile_serializer.save()

    return Response({
        "success": True,
        "message": "User updated successfully.",
        "user": UserManagementSerializer(target_user).data,
    })


@api_view(["PATCH", "POST"])
@permission_classes([IsAuthenticated])
def user_status_update(request, user_id):
    if not _is_admin_user(request.user):
        return _admin_denied()

    User = get_user_model()
    try:
        target_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if target_user.pk == request.user.pk:
        return Response(
            {"success": False, "message": "You cannot change your own account status."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_status = str(request.data.get("status", "")).strip()
    allowed = {choice[0] for choice in UserProfile.STATUS_CHOICES}
    if new_status not in allowed:
        return Response(
            {"success": False, "message": f"Status must be one of: {', '.join(sorted(allowed))}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile = _ensure_user_profile(target_user)
    profile.status = new_status
    profile.save(update_fields=["status", "updated_at"])
    target_user.is_active = (new_status == "Active")
    target_user.save(update_fields=["is_active"])

    return Response({
        "success": True,
        "message": "User status updated successfully.",
        "user_id": target_user.id,
        "status": profile.status,
        "is_active": target_user.is_active,
    })


# ------------------------- ADMIN EMAIL OTP -------------------------

def _otp_digest(otp):
    # Pepper the hash with the Django secret key; never store the raw OTP.
    return hashlib.sha256(f"{settings.SECRET_KEY}:{otp}".encode("utf-8")).hexdigest()

@api_view(["POST"])
@permission_classes([AllowAny])
def admin_send_otp(request):
    User = get_user_model()

    email = str(request.data.get("email", "")).strip()

    if not email:
        return Response(
            {"success": False, "message": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find an active admin account with this email.
    admin_users = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    ).order_by("-id")

    admin_user = admin_users.first()

    if not admin_user or not _is_admin_user(admin_user):
        return _admin_denied()

    if not admin_user.email:
        return Response(
            {"success": False, "message": "Admin email is missing."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()

    AdminEmailOTP.objects.filter(
        user=admin_user,
        is_used=False
    ).update(is_used=True)

    otp_record = AdminEmailOTP.objects.create(
        user=admin_user,
        otp_hash=_otp_digest(otp),
        expires_at=now + timedelta(minutes=5),
    )

    try:
        send_mail(
            subject="RailVision AI - Admin verification code",
            message=(
                f"Your RailVision AI admin verification code is {otp}. "
                "It expires in 5 minutes. Do not share this code."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_user.email],
            fail_silently=False,
        )

    except Exception:
        logger.exception("Could not send admin OTP email.")
        otp_record.delete()

        return Response(
            {
                "success": False,
                "message": "OTP email could not be sent. Check email configuration.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        "success": True,
        "message": "Verification code sent to registered email.",
        "expires_in_seconds": 300,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_verify_otp(request):
    User = get_user_model()

    email = str(request.data.get("email", "")).strip()
    otp = str(request.data.get("otp", "")).strip()

    if not email or not re.fullmatch(r"\d{6}", otp):
        return Response(
            {
                "success": False,
                "message": "Valid email and 6-digit OTP are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    admin_user = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    ).order_by("-id").first()

    if not admin_user or not _is_admin_user(admin_user):
        return _admin_denied()

    otp_record = AdminEmailOTP.objects.filter(
        user=admin_user,
        is_used=False,
    ).order_by("-created_at").first()

    if not otp_record:
        return Response(
            {
                "success": False,
                "message": "No active verification code. Request a new code.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp_record.expires_at <= timezone.now():
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        return Response(
            {"success": False, "message": "Verification code has expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp_record.attempts >= 5:
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        return Response(
            {"success": False, "message": "Too many attempts. Request a new code."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    otp_record.attempts += 1

    if not secrets.compare_digest(otp_record.otp_hash, _otp_digest(otp)):
        if otp_record.attempts >= 5:
            otp_record.is_used = True

        otp_record.save(update_fields=["attempts", "is_used"])

        return Response(
            {"success": False, "message": "Invalid verification code."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_record.is_used = True
    otp_record.save(update_fields=["is_used"])

    refresh = RefreshToken.for_user(admin_user)

    return Response({
        "success": True,
        "message": "Admin login successful.",
        "verified": True,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": admin_user.id,
            "username": admin_user.username,
            "email": admin_user.email,
            "role": "Admin",
        },
    })

# ------------------------- PLATFORM MANAGEMENT -------------------------

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def platform_list(request):
    if request.method == "GET":
        platforms = Platform.objects.select_related("station").all().order_by(
            "station__station_name", "platform_number"
        )
        station_id = request.query_params.get("station_id")
        if station_id:
            if not str(station_id).isdigit():
                return Response(
                    {"success": False, "message": "station_id must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            platforms = platforms.filter(station_id=int(station_id))
        return Response({
            "success": True,
            "count": platforms.count(),
            "results": PlatformSerializer(platforms, many=True).data,
        })

    if not _is_admin_user(request.user):
        return _admin_denied()

    serializer = PlatformSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        platform = serializer.save()
        create_station_activity(
            request, f"Platform {platform.platform_number} added",
            "add", f"Platform {platform.platform_number} added at {platform.station.station_name}."
        )
    return Response(
        {"success": True, "message": "Platform created.", "platform": PlatformSerializer(platform).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def platform_detail(request, platform_id):
    try:
        platform = Platform.objects.select_related("station").get(pk=platform_id)
    except Platform.DoesNotExist:
        return Response(
            {"success": False, "message": "Platform not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response({"success": True, "platform": PlatformSerializer(platform).data})

    if not _is_admin_user(request.user):
        return _admin_denied()

    if request.method == "DELETE":
        label = f"{platform.station.station_name} platform {platform.platform_number}"
        with transaction.atomic():
            create_station_activity(request, "Platform deleted", "delete", f"{label} deleted.")
            platform.delete()
        return Response({"success": True, "message": "Platform deleted."})

    serializer = PlatformSerializer(
        platform, data=request.data, partial=(request.method == "PATCH")
    )
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        platform = serializer.save()
        create_station_activity(
            request, "Platform updated", "update",
            f"Platform {platform.platform_number} at {platform.station.station_name} updated."
        )
    return Response({"success": True, "message": "Platform updated.", "platform": serializer.data})


# ------------------------- RECENT ADMIN ACTIVITIES -------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_recent_activities(request):
    if not _is_admin_user(request.user):
        return _admin_denied()

    limit = request.query_params.get("limit", "10")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 10

    activities = ActivityLog.objects.all().order_by("-created_at")[:limit]
    from .serializers import ActivityLogSerializer
    return Response({
        "success": True,
        "count": len(activities),
        "results": ActivityLogSerializer(activities, many=True).data,
    })


# ------------------------- FACILITY ADMIN CRUD -------------------------

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def admin_facility_list(request):
    if request.method == "GET" and not _is_admin_user(request.user):
        return _admin_denied()
    if request.method == "POST" and not _is_admin_user(request.user):
        return _admin_denied()

    if request.method == "GET":
        facilities = Facility.objects.select_related("station", "platform").all().order_by("-created_at")
        station_id = request.query_params.get("station_id")
        verification_status = request.query_params.get("verification_status")
        if station_id:
            facilities = facilities.filter(station_id=station_id)
        if verification_status:
            facilities = facilities.filter(verification_status__iexact=verification_status)
        return Response({
            "success": True,
            "count": facilities.count(),
            "results": FacilitySerializer(facilities, many=True).data,
        })

    serializer = FacilitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        facility = serializer.save()
        create_station_activity(
            request, f"Facility {facility.facility_name} added", "add",
            f"{facility.facility_name} added at {facility.station.station_name}."
        )
    return Response(
        {"success": True, "message": "Facility created.", "facility": FacilitySerializer(facility).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def admin_facility_detail(request, facility_id):
    try:
        facility = Facility.objects.select_related("station", "platform").get(pk=facility_id)
    except Facility.DoesNotExist:
        return Response(
            {"success": False, "message": "Facility not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _is_admin_user(request.user):
        return _admin_denied()

    if request.method == "GET":
        return Response({"success": True, "facility": FacilitySerializer(facility).data})

    if request.method == "DELETE":
        label = facility.facility_name
        with transaction.atomic():
            create_station_activity(request, f"Facility {label} deleted", "delete", f"{label} deleted.")
            facility.delete()
        return Response({"success": True, "message": "Facility deleted."})

    serializer = FacilitySerializer(
        facility, data=request.data, partial=(request.method == "PATCH")
    )
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        facility = serializer.save()
        create_station_activity(
            request, f"Facility {facility.facility_name} updated", "update",
            f"{facility.facility_name} at {facility.station.station_name} updated."
        )
    return Response({"success": True, "message": "Facility updated.", "facility": serializer.data})


# ------------------------- RAILWAY DOCUMENT ADMIN CRUD -------------------------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admin_document_list(request):
    if not _is_admin_user(request.user):
        return _admin_denied()

    if request.method == "GET":
        documents = RailwayDocument.objects.select_related("uploaded_by", "verified_by").all().order_by("-uploaded_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            documents = documents.filter(verification_status__iexact=status_filter)
        return Response({
            "success": True,
            "count": documents.count(),
            "results": RailwayDocumentSerializer(documents, many=True, context={"request": request}).data,
        })

    serializer = RailwayDocumentSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    document = serializer.save(uploaded_by=request.user)
    ActivityLog.objects.create(
        action=f"Document {document.title} uploaded",
        performed_by=get_station_admin_name(request),
        activity_type="upload",
        description=f"{document.original_filename or document.title} uploaded.",
    )
    return Response(
        {"success": True, "message": "Document uploaded.", "document": RailwayDocumentSerializer(document, context={"request": request}).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def admin_document_detail(request, document_id):
    if not _is_admin_user(request.user):
        return _admin_denied()

    try:
        document = RailwayDocument.objects.select_related("uploaded_by", "verified_by").get(pk=document_id)
    except RailwayDocument.DoesNotExist:
        return Response(
            {"success": False, "message": "Document not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response({
            "success": True,
            "document": RailwayDocumentSerializer(document, context={"request": request}).data,
        })

    if request.method == "DELETE":
        title = document.title
        document.delete()
        ActivityLog.objects.create(
            action=f"Document {title} deleted",
            performed_by=get_station_admin_name(request),
            activity_type="delete",
            description=f"Document {title} deleted.",
        )
        return Response({"success": True, "message": "Document deleted."})

    serializer = RailwayDocumentSerializer(
        document, data=request.data, partial=(request.method == "PATCH"),
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    document = serializer.save()
    return Response({
        "success": True,
        "message": "Document updated.",
        "document": RailwayDocumentSerializer(document, context={"request": request}).data,
    })


@api_view(["POST", "PATCH"])
@permission_classes([IsAuthenticated])
def verify_railway_document(request, document_id):
    if not _is_admin_user(request.user):
        return _admin_denied()

    try:
        document = RailwayDocument.objects.get(pk=document_id)
    except RailwayDocument.DoesNotExist:
        return Response(
            {"success": False, "message": "Document not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    verification_status = str(request.data.get("verification_status", "")).strip().title()
    if verification_status not in {"Approved", "Rejected", "Pending"}:
        return Response(
            {"success": False, "message": "verification_status must be Approved, Rejected or Pending."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    document.verification_status = verification_status
    document.verification_remarks = str(request.data.get("verification_remarks", "")).strip()
    document.verified_by = request.user
    document.verified_at = timezone.now()
    document.save(update_fields=[
        "verification_status", "verification_remarks", "verified_by", "verified_at"
    ])

    ActivityLog.objects.create(
        action=f"Document {document.title} {verification_status.lower()}",
        performed_by=get_station_admin_name(request),
        activity_type="verify",
        description=f"Document verification status changed to {verification_status}.",
    )
    return Response({
        "success": True,
        "message": f"Document {verification_status.lower()} successfully.",
        "document": RailwayDocumentSerializer(document, context={"request": request}).data,
    })


# ------------------------- ADMIN DASHBOARD -------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_dashboard_stats(request):
    if not _is_admin_user(request.user):
        return _admin_denied()

    User = get_user_model()
    profiles = UserProfile.objects.all()
    return Response({
        "success": True,
        "stats": {
            "total_users": User.objects.count(),
            "active_users": profiles.filter(status="Active").count(),
            "inactive_users": profiles.filter(status="Inactive").count(),
            "blocked_users": profiles.filter(status="Blocked").count(),
            "total_stations": Station.objects.count(),
            "total_platforms": Platform.objects.count(),
            "total_facilities": Facility.objects.count(),
            "pending_facilities": Facility.objects.filter(verification_status="Pending").count(),
            "total_documents": RailwayDocument.objects.count(),
            "pending_documents": RailwayDocument.objects.filter(verification_status="Pending").count(),
            "approved_documents": RailwayDocument.objects.filter(verification_status="Approved").count(),
            "rejected_documents": RailwayDocument.objects.filter(verification_status="Rejected").count(),
        },
    })


