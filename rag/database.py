import re
import logging

from api.models import Station, Platform, Facility


logger = logging.getLogger(__name__)


# ============================================================
# 1. STATION ALIASES
# ============================================================

# Question aliases and corresponding database station names.
# Add more aliases here according to your database records.

STATION_ALIASES = {

    "satna": {
        "question_names": [
            "satna",
            "satna junction",
            "satna railway station",
            "सतना",
            "सतना जंक्शन",
            "सतना रेलवे स्टेशन",
            "सतना स्टेशन",
        ],
        "database_names": [
            "satna",
            "satna junction",
            "satna railway station",
            "sta",
        ],
    },

    "bhopal": {
        "question_names": [
            "bhopal",
            "bhopal junction",
            "bhopal railway station",
            "भोपाल",
            "भोपाल जंक्शन",
            "भोपाल रेलवे स्टेशन",
            "भोपाल स्टेशन",
        ],
        "database_names": [
            "bhopal",
            "bhopal junction",
            "भोपाल",
            "भोपाल जंक्शन",
            "bpl",
        ],
    },

    "rani kamalapati": {
        "question_names": [
            "rani kamalapati",
            "habibganj",
            "रानी कमलापति",
            "हबीबगंज",
        ],
        "database_names": [
            "rani kamalapati",
            "habibganj",
            "रानी कमलापति",
            "rkmp",
        ],
    },

    "indore": {
        "question_names": [
            "indore",
            "indore junction",
            "इंदौर",
            "इंदौर जंक्शन",
        ],
        "database_names": [
            "indore",
            "indore junction",
            "इंदौर",
            "ind",
        ],
    },

    "ujjain": {
        "question_names": [
            "ujjain",
            "ujjain junction",
            "उज्जैन",
            "उज्जैन जंक्शन",
        ],
        "database_names": [
            "ujjain",
            "ujjain junction",
            "उज्जैन",
            "ujn",
        ],
    },

    "jabalpur": {
        "question_names": [
            "jabalpur",
            "jabalpur junction",
            "जबलपुर",
            "जबलपुर जंक्शन",
        ],
        "database_names": [
            "jabalpur",
            "jabalpur junction",
            "जबलपुर",
            "jbp",
        ],
    },

    "itarsi": {
        "question_names": [
            "itarsi",
            "itarsi junction",
            "इटारसी",
        ],
        "database_names": [
            "itarsi",
            "itarsi junction",
            "इटारसी",
            "et",
        ],
    },

    "katni": {
        "question_names": [
            "katni",
            "katni junction",
            "कटनी",
            "कटनी जंक्शन",
        ],
        "database_names": [
            "katni",
            "katni junction",
            "कटनी",
            "kTE",
        ],
    },

    "rewa": {
        "question_names": [
            "rewa",
            "रीवा",
        ],
        "database_names": [
            "rewa",
            "रीवा",
            "rewa station",
        ],
    },

    "sagar": {
        "question_names": [
            "sagar",
            "saugor",
            "सागर",
        ],
        "database_names": [
            "sagar",
            "saugor",
            "सागर",
        ],
    },

    "khandwa": {
        "question_names": [
            "khandwa",
            "खंडवा",
        ],
        "database_names": [
            "khandwa",
            "खंडवा",
        ],
    },

    "burhanpur": {
        "question_names": [
            "burhanpur",
            "बुरहानपुर",
        ],
        "database_names": [
            "burhanpur",
            "बुरहानपुर",
        ],
    },

    "nagda": {
        "question_names": [
            "nagda",
            "nagda junction",
            "नागदा",
            "नागदा जंक्शन",
        ],
        "database_names": [
            "nagda",
            "nagda junction",
            "नागदा",
        ],
    },
}


# ============================================================
# 2. NORMALIZE TEXT
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower().strip()

    # Remove punctuation
    text = re.sub(r"[?!.,।,:;\"']", " ", text)

    # Normalize extra spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# 3. SAFE WORD MATCHING
# ============================================================

def contains_phrase(text, phrase):

    text = normalize_text(text)
    phrase = normalize_text(phrase)

    if not text or not phrase:
        return False

    # Hindi and English phrase matching
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"

    return bool(re.search(pattern, text))


# ============================================================
# 4. FIND STATION
# ============================================================

def find_station(question):

    question = normalize_text(question)

    if not question:
        return None

    stations = list(Station.objects.all())

    # --------------------------------------------------------
    # STEP 1: Find matching station alias in question
    # --------------------------------------------------------

    matched_key = None
    matched_length = 0

    for station_key, config in STATION_ALIASES.items():

        for alias in config["question_names"]:

            if contains_phrase(question, alias):

                # Prefer the longest matching alias.
                if len(alias) > matched_length:

                    matched_key = station_key
                    matched_length = len(alias)

    # --------------------------------------------------------
    # STEP 2: Match alias with actual database station
    # --------------------------------------------------------

    if matched_key:

        database_aliases = STATION_ALIASES[
            matched_key
        ]["database_names"]

        matched_stations = []

        for station in stations:

            database_fields = [

                station.station_name,
                station.station_code,
                station.city,

            ]

            for field_value in database_fields:

                if not field_value:
                    continue

                db_value = normalize_text(field_value)

                for alias in database_aliases:

                    alias = normalize_text(alias)

                    if contains_phrase(db_value, alias):

                        matched_stations.append(station)
                        break

                else:
                    continue

                break

        # Return only if exactly one station matches.
        if len(matched_stations) == 1:

            station = matched_stations[0]

            logger.info(
                "STATION IDENTIFIED: %s",
                station.station_name
            )

            return station

        if len(matched_stations) > 1:

            logger.warning(
                "Multiple database stations matched alias: %s",
                matched_key
            )

            return None

        logger.warning(
            "Station alias '%s' found in question, "
            "but no matching database record exists.",
            matched_key
        )

        return None

    # --------------------------------------------------------
    # STEP 3: Fallback database name matching
    # --------------------------------------------------------

    matched_stations = []

    for station in stations:

        database_fields = [

            station.station_name,
            station.station_code,
            station.city,

        ]

        for field_value in database_fields:

            if not field_value:
                continue

            db_value = normalize_text(field_value)

            if contains_phrase(question, db_value):

                matched_stations.append(station)
                break

    # Remove duplicate station records
    unique_stations = {
        station.id: station
        for station in matched_stations
    }

    if len(unique_stations) == 1:

        station = list(unique_stations.values())[0]

        logger.info(
            "STATION IDENTIFIED BY DATABASE NAME: %s",
            station.station_name
        )

        return station

    if len(unique_stations) > 1:

        logger.warning(
            "Multiple stations matched question: %s",
            question
        )

    return None


# ============================================================
# 5. DETECT PLATFORM COUNT QUESTION
# ============================================================

def is_platform_count_question(question):

    question = normalize_text(question)

    platform_keywords = [

        "platform",
        "platforms",
        "प्लेटफॉर्म",
        "प्लेटफार्म",
        "प्लेटफॉर्मों",
        "प्लेटफार्मों",
        "प्लेटफॉर्म्स",

    ]

    count_keywords = [

        "total",
        "how many",
        "how much",
        "number",
        "count",
        "kitna",
        "kitne",
        "kitni",
        "कितने",
        "कितना",
        "कितनी",
        "कुल",
        "संख्या",

    ]

    has_platform = any(
        contains_phrase(question, word)
        for word in platform_keywords
    )

    has_count = any(
        contains_phrase(question, word)
        for word in count_keywords
    )

    return has_platform and has_count


# ============================================================
# 6. GET PLATFORM COUNT
# ============================================================

def get_platform_count(station):

    # First priority: actual Platform database records.
    platform_count = Platform.objects.filter(
        station=station
    ).count()

    if platform_count > 0:

        return platform_count

    # Second priority: station model platform_count field.
    stored_count = getattr(
        station,
        "platform_count",
        0
    )

    if stored_count:

        return int(stored_count)

    return 0


# ============================================================
# 7. FACILITY QUESTION DETECTION
# ============================================================

FACILITY_KEYWORDS = {

    "waiting room": "waiting_room",
    "waiting": "waiting_room",
    "प्रतीक्षालय": "waiting_room",
    "वेटिंग रूम": "waiting_room",

    "restroom": "restroom",
    "toilet": "restroom",
    "washroom": "restroom",
    "शौचालय": "restroom",
    "टॉयलेट": "restroom",

    "ticket counter": "ticket_counter",
    "ticket": "ticket_counter",
    "टिकट काउंटर": "ticket_counter",

    "parking": "parking",
    "पार्किंग": "parking",

    "food court": "food_court",
    "food": "food_court",
    "restaurant": "food_court",
    "खाना": "food_court",
    "भोजन": "food_court",

    "atm": "atm",

    "medical": "medical",
    "hospital": "medical",
    "चिकित्सा": "medical",
    "अस्पताल": "medical",

    "drinking water": "water",
    "water": "water",
    "पानी": "water",

}


# ============================================================
# 8. GET FACILITY ANSWER
# ============================================================

def get_facility_answer(station, question):

    question = normalize_text(question)

    selected_type = None

    # Longer keywords should be checked first.
    sorted_keywords = sorted(
        FACILITY_KEYWORDS.items(),
        key=lambda item: len(item[0]),
        reverse=True
    )

    for keyword, facility_type in sorted_keywords:

        if contains_phrase(question, keyword):

            selected_type = facility_type
            break

    if not selected_type:

        return None

    facilities = Facility.objects.filter(
        station=station,
        facility_type=selected_type
    ).select_related("platform")

    if not facilities.exists():

        return (
            f"No {selected_type.replace('_', ' ')} "
            f"record was found at {station.station_name} "
            "in the RailVision database."
        )

    results = []

    for facility in facilities:

        location = str(
            getattr(facility, "facility_name", "Facility")
        )

        platform = getattr(
            facility,
            "platform",
            None
        )

        if platform:

            platform_number = getattr(
                platform,
                "platform_number",
                None
            )

            if platform_number is not None:

                location += (
                    f", Platform {platform_number}"
                )

        description = getattr(
            facility,
            "description",
            ""
        )

        if description:

            location += f". {description}"

        notes = getattr(
            facility,
            "additional_notes",
            ""
        )

        if notes:

            location += f". Notes: {notes}"

        results.append(location)

    return (
        f"Facilities available at {station.station_name}: "
        + "; ".join(results)
    )


# ============================================================
# 9. MAIN DATABASE ANSWER FUNCTION
# ============================================================

def get_station_answer(question):

    question = normalize_text(question)

    if not question:

        return None

    logger.info(
        "DATABASE QUESTION: %s",
        question
    )

    # --------------------------------------------------------
    # STEP 1: Identify station
    # --------------------------------------------------------

    station = find_station(question)

    if not station:

        logger.warning(
            "DATABASE: Station not identified for question: %s",
            question
        )

        return None

    logger.info(
        "DATABASE: Selected station: %s",
        station.station_name
    )

    # --------------------------------------------------------
    # STEP 2: Platform count
    # --------------------------------------------------------

    if is_platform_count_question(question):

        platform_count = get_platform_count(station)

        logger.info(
            "DATABASE: Platform count for %s = %s",
            station.station_name,
            platform_count
        )

        if platform_count == 0:

            return (
                f"Platform count for {station.station_name} "
                "is not available in the RailVision database."
            )

        return (
            f"{station.station_name} has a total of "
            f"{platform_count} platforms."
        )

    # --------------------------------------------------------
    # STEP 3: Facility information
    # --------------------------------------------------------

    facility_answer = get_facility_answer(
        station,
        question
    )

    if facility_answer:

        return facility_answer

    # --------------------------------------------------------
    # STEP 4: No matching database information
    # --------------------------------------------------------

    logger.info(
        "DATABASE: No matching information found."
    )

    return None