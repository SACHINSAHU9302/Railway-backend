from django.urls import path
from .views import (
    user_profile,
    admin_profile,
    user_list,
    user_detail,
    user_status_update,
)
from .views import admin_send_otp, admin_verify_otp
from .views import platform_list, platform_detail
from .views import admin_recent_activities
from .views import admin_facility_list, admin_facility_detail
from .views import (
    admin_document_list,
    admin_document_detail,
    verify_railway_document,
)

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView  # type: ignore[import-not-found]
from .views import (

    document_list,
    rag_query,
    station_detail,
    station_list,
    facility_list,

    RegisterView,
    admin_dashboard_stats,
    ticket_scanner_health,
    extract_ticket,
    validate_ticket_pnr,
)

from .serializers import EmailTokenObtainPairSerializer

urlpatterns = [
        # ========================================================
    # USER MANAGEMENT
    # ========================================================

    path(
        "users/",
        user_list,
        name="user_list",
    ),

    path(
        "users/<int:user_id>/",
        user_detail,
        name="user_detail",
    ),

    path(
        "users/<int:user_id>/status/",
        user_status_update,
        name="user_status_update",
    ),
    # Admin Document Management

path(
    "admin/documents/",
    admin_document_list,
    name="admin_document_list"
),

path(
    "admin/documents/<int:document_id>/",
    admin_document_detail,
    name="admin_document_detail"
),

path(
    "admin/documents/<int:document_id>/verify/",
    verify_railway_document,
    name="verify_railway_document"
),
    # Admin Facility Management

path(
    "admin/facilities/",
    admin_facility_list,
    name="admin_facility_list"
),

path(
    "admin/facilities/<int:facility_id>/",
    admin_facility_detail,
    name="admin_facility_detail"
),
    # Admin Platform Management

path(
    "platforms/",
    platform_list,
    name="platform_list"
),

path(
    "platforms/<int:platform_id>/",
    platform_detail,
    name="platform_detail"
),

    # Admin Recent Activities
    path(
    "admin/activities/",
    admin_recent_activities,
    name="admin_recent_activities"
),
    #ADMIN DASHBOARD STATS
    path(
    "admin/dashboard/",
    admin_dashboard_stats,
    name="admin_dashboard_stats"
),
    # Admin Profile
path(
    "auth/admin/profile/",
    admin_profile,
    name="admin_profile",
),
    
    #user profile 
    path("auth/profile/", user_profile, name="user_profile"),
    
    # Send a login OTP to an authorized admin
path(
    "auth/admin/send-otp/",
    admin_send_otp,
    name="admin_send_otp",
),

# Verify the OTP and return JWT tokens
path(
    "auth/admin/verify-otp/",
    admin_verify_otp,
    name="admin_verify_otp",
),

    # User Registration
    path(
        "auth/register/",
        RegisterView.as_view(),
        name="register",
    ),

    # JWT Login using Email and Password
    path(
        "auth/token/",
        TokenObtainPairView.as_view(
            serializer_class=EmailTokenObtainPairSerializer
        ),
        name="token_obtain_pair",
    ),

    # JWT Refresh Token
    path(
        "auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),

    # Station Navigation
    path(
        "stations/",
        station_list,
        name="station_list",
    ),
    path(
        "stations/<int:station_id>/",
        station_detail,
        name="station_detail",
    ),

    # Facility Finder
    path("facilities/", facility_list, name="facility_list"),
     path("documents/", document_list, name="document_list"),
     # Ticket Scanner
path(
    "ticket/health/",
    ticket_scanner_health,
    name="ticket_scanner_health",
),
path(
    "ticket/extract/",
    extract_ticket,
    name="extract_ticket",
),
path(
    "ticket/pnr/",
    validate_ticket_pnr,
    name="validate_ticket_pnr",
),
# RAG Voice Assistant
path(
    "rag/query/",
    rag_query,
    name="rag_query"
),
]

