import json
import logging
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from pathlib import Path
from django.conf import settings
from rag.chain import ask_rag
from .models import Station, Platform, Facility

logger = logging.getLogger(__name__)

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
# 2. STATION LIST API
# Endpoint: GET /api/stations/
# ============================================================

@require_GET
def station_list(request):
    """
    Return all railway stations.
    """

    stations = Station.objects.all().order_by("station_name")

    data = []

    for station in stations:
        data.append(
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
        )

    return JsonResponse(
        {
            "success": True,
            "count": len(data),
            "results": data,
        }
    )


# ============================================================
# 3. STATION DETAIL API
# Endpoint: GET /api/stations/<station_id>/
# ============================================================

@require_GET
def station_detail(request, station_id):
    """
    Return station details, platforms and facilities.
    """

    try:
        station = Station.objects.get(id=station_id)

    except Station.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": "Station not found.",
            },
            status=404,
        )

    platforms = station.platforms.all().order_by("platform_number")

    facilities = (
        station.facilities
        .select_related("platform")
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
        for facility in facilities
    ]

    return JsonResponse(
        {
            "success": True,
            "station": station_data,
            "platforms": platform_data,
            "facilities": facility_data,
        }
    )


# ============================================================
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
