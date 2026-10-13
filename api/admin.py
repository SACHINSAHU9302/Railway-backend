from django.contrib import admin

from .models import (
    Station,
    Platform,
    Facility,
    Train,
)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):

    list_display = (
        "station_code",
        "station_name",
        "city",
        "state",
        "platform_count",
    )

    search_fields = (
        "station_code",
        "station_name",
        "city",
    )


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):

    list_display = (
        "station",
        "platform_number",
        "accessibility",
    )

    list_filter = (
        "accessibility",
    )

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):

    list_display = (
        "facility_name",
        "facility_type",
        "station",
        "platform",
        "accessibility",
    )

    list_filter = (
        "facility_type",
        "accessibility",
    )

    search_fields = (
        "facility_name",
        "station__station_name",
    )

@admin.register(Train)
class TrainAdmin(admin.ModelAdmin):

    list_display = (
        "train_number",
        "train_name",
        "source",
        "destination",
        "active",
    )
    search_fields = (
        "train_number",
        "train_name",
        "source",
        "destination",
    )