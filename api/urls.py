from django.urls import path
from .views import  document_list, rag_query, station_detail, station_list, facility_list


urlpatterns = [
    path("rag/query/", rag_query, name="rag_query"),
    
       # Station Navigation
    path("stations/", station_list, name="station_list"),
    path(
        "stations/<int:station_id>/",
        station_detail,
        name="station_detail",
    ),

    # Facility Finder
    path("facilities/", facility_list, name="facility_list"),
     path("documents/", document_list, name="document_list"),
]
