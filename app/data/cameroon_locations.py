SUPPLY_HUBS = {
    "douala":    {"name": "Douala",    "lat": 4.0511, "lng": 9.7679,  "region": "Littoral"},
    "yaounde":   {"name": "Yaoundé",   "lat": 3.848,  "lng": 11.502,  "region": "Centre"},
    "bafoussam": {"name": "Bafoussam", "lat": 5.476,  "lng": 10.417,  "region": "West"},
    "bamenda":   {"name": "Bamenda",   "lat": 5.963,  "lng": 10.159,  "region": "North-West"},
    "garoua":    {"name": "Garoua",    "lat": 9.3015, "lng": 13.3975, "region": "North"},
    "maroua":    {"name": "Maroua",    "lat": 10.591, "lng": 14.315,  "region": "Far North"},
    "bertoua":   {"name": "Bertoua",   "lat": 4.577,  "lng": 13.684,  "region": "East"},
    "kribi":     {"name": "Kribi",     "lat": 2.937,  "lng": 9.907,   "region": "South"},
}

LEGACY_REGION_MAP = {
    "Douala": "Littoral",
    "Yaoundé": "Centre",
    "Coastal": "South-West",
    "Centre": "Centre",
    "Center": "Centre",
}


def map_region_name(region: str) -> str:
    return LEGACY_REGION_MAP.get(region, region)


def get_division_for_location(region: str):
    mapped = map_region_name(region)
    defaults = {
        "Littoral": ("Littoral", "Wouri"),
        "Centre": ("Centre", "Mfoundi"),
        "West": ("West", "Mifi"),
        "North-West": ("North-West", "Mezam"),
        "North": ("North", "Bénoué"),
        "Adamaoua": ("Adamaoua", "Vina"),
        "Far North": ("Far North", "Diamaré"),
        "South": ("South", "Mvila"),
        "East": ("East", "Lom-et-Djérem"),
        "South-West": ("South-West", "Fako"),
    }
    result = defaults.get(mapped, ("Centre", "Mfoundi"))
    return {"region_name": result[0], "division_name": result[1]}


REGIONS = [
    {
        "name": "Littoral",
        "name_fr": "Littoral",
        "capital": "Douala",
        "soil_type": "Clay / Marshy alluvial deposits",
        "hazard_count": 3,
        "foundation": "Elevated raft foundation (radier surélevé) with drainage",
        "climate_tip": "High humidity and rainfall. Design for maximum natural cross-ventilation, wide verandas, and anti-corrosion materials.",
        "divisions": [
            {"name": "Wouri", "capital": "Douala", "transport_index": 1.00, "logistics_difficulty": "low", "surcharge_pct": 0},
            {"name": "Moungo", "capital": "Nkongsamba", "transport_index": 1.03, "logistics_difficulty": "low", "surcharge_pct": 1},
            {"name": "Nkam", "capital": "Yabassi", "transport_index": 1.08, "logistics_difficulty": "moderate", "surcharge_pct": 3},
            {"name": "Sanaga-Maritime", "capital": "Édéa", "transport_index": 1.05, "logistics_difficulty": "low", "surcharge_pct": 2},
        ],
    },
    {
        "name": "Centre",
        "name_fr": "Centre",
        "capital": "Yaoundé",
        "soil_type": "Laterite / Rocky ferralitic soil",
        "hazard_count": 2,
        "foundation": "Strip footing (semelles filantes) on stable laterite",
        "climate_tip": "Mild equatorial climate with two rainy seasons. Standard construction with good cross-ventilation works well.",
        "divisions": [
            {"name": "Mfoundi", "capital": "Yaoundé", "transport_index": 1.06, "logistics_difficulty": "low", "surcharge_pct": 2},
            {"name": "Haute-Sanaga", "capital": "Nanga-Eboko", "transport_index": 1.12, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Lekié", "capital": "Monatélé", "transport_index": 1.10, "logistics_difficulty": "moderate", "surcharge_pct": 4},
            {"name": "Mbam-et-Inoubou", "capital": "Bafia", "transport_index": 1.12, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Mbam-et-Kim", "capital": "Ntui", "transport_index": 1.14, "logistics_difficulty": "moderate", "surcharge_pct": 6},
            {"name": "Méfou-et-Afamba", "capital": "Mfou", "transport_index": 1.08, "logistics_difficulty": "low", "surcharge_pct": 3},
            {"name": "Méfou-et-Akono", "capital": "Ngoumou", "transport_index": 1.09, "logistics_difficulty": "low", "surcharge_pct": 3},
            {"name": "Nyong-et-Kéllé", "capital": "Éséka", "transport_index": 1.10, "logistics_difficulty": "moderate", "surcharge_pct": 4},
            {"name": "Nyong-et-Mfoumou", "capital": "Akonolinga", "transport_index": 1.15, "logistics_difficulty": "moderate", "surcharge_pct": 6},
            {"name": "Nyong-et-So'o", "capital": "Mbalmayo", "transport_index": 1.10, "logistics_difficulty": "low", "surcharge_pct": 4},
        ],
    },
    {
        "name": "West",
        "name_fr": "Ouest",
        "capital": "Bafoussam",
        "soil_type": "Volcanic / Andosol",
        "hazard_count": 3,
        "foundation": "Reinforced strip footing on stable volcanic soil with drainage",
        "climate_tip": "Highland tropical climate with heavy rainfall. Deep roof overhangs, robust surface drainage, slope-stabilized foundation.",
        "divisions": [
            {"name": "Mifi", "capital": "Bafoussam", "transport_index": 1.10, "logistics_difficulty": "low", "surcharge_pct": 4},
            {"name": "Bamboutos", "capital": "Mbouda", "transport_index": 1.14, "logistics_difficulty": "moderate", "surcharge_pct": 6},
            {"name": "Haut-Nkam", "capital": "Bafang", "transport_index": 1.12, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Hauts-Plateaux", "capital": "Baham", "transport_index": 1.13, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Koung-Khi", "capital": "Bandjoun", "transport_index": 1.11, "logistics_difficulty": "low", "surcharge_pct": 4},
            {"name": "Ménoua", "capital": "Dschang", "transport_index": 1.13, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Ndé", "capital": "Bangangté", "transport_index": 1.14, "logistics_difficulty": "moderate", "surcharge_pct": 6},
            {"name": "Noun", "capital": "Foumban", "transport_index": 1.16, "logistics_difficulty": "high", "surcharge_pct": 7},
        ],
    },
    {
        "name": "North",
        "name_fr": "Nord",
        "capital": "Garoua",
        "soil_type": "Sandy / Ferruginous tropical soil",
        "hazard_count": 3,
        "foundation": "Standard strip footing, deep if necessary for stable bearing",
        "climate_tip": "Hot semi-arid Sahel climate. High thermal mass walls, high ceilings, small shaded openings, and cross-ventilation to reduce heat gain.",
        "divisions": [
            {"name": "Bénoué", "capital": "Garoua", "transport_index": 1.18, "logistics_difficulty": "moderate", "surcharge_pct": 8},
            {"name": "Faro", "capital": "Poli", "transport_index": 1.25, "logistics_difficulty": "high", "surcharge_pct": 12},
            {"name": "Mayo-Louti", "capital": "Guider", "transport_index": 1.20, "logistics_difficulty": "moderate", "surcharge_pct": 9},
            {"name": "Mayo-Rey", "capital": "Tcholliré", "transport_index": 1.24, "logistics_difficulty": "high", "surcharge_pct": 11},
        ],
    },
    {
        "name": "Adamaoua",
        "name_fr": "Adamaoua",
        "capital": "Ngaoundéré",
        "soil_type": "Lateritic / Granitic",
        "hazard_count": 3,
        "foundation": "Strip or pad foundation on stable laterite",
        "climate_tip": "Highland tropical climate, cooler than the rest of the country. Standard construction adapted for temperature variations.",
        "divisions": [
            {"name": "Vina", "capital": "Ngaoundéré", "transport_index": 1.20, "logistics_difficulty": "moderate", "surcharge_pct": 9},
            {"name": "Djérem", "capital": "Tibati", "transport_index": 1.26, "logistics_difficulty": "high", "surcharge_pct": 13},
            {"name": "Faro-et-Déo", "capital": "Tignère", "transport_index": 1.30, "logistics_difficulty": "high", "surcharge_pct": 15},
            {"name": "Mayo-Banyo", "capital": "Banyo", "transport_index": 1.28, "logistics_difficulty": "high", "surcharge_pct": 14},
            {"name": "Mbéré", "capital": "Meiganga", "transport_index": 1.30, "logistics_difficulty": "high", "surcharge_pct": 15},
        ],
    },
    {
        "name": "North-West",
        "name_fr": "Nord-Ouest",
        "capital": "Bamenda",
        "soil_type": "Volcanic / Basaltic",
        "hazard_count": 3,
        "foundation": "Reinforced foundation on volcanic soil with good drainage",
        "climate_tip": "Cool highland climate with distinct wet/dry seasons. Deep roof overhangs, robust drainage, slope-adapted layout.",
        "divisions": [
            {"name": "Mezam", "capital": "Bamenda", "transport_index": 1.14, "logistics_difficulty": "moderate", "surcharge_pct": 6},
            {"name": "Boyo", "capital": "Fundong", "transport_index": 1.22, "logistics_difficulty": "high", "surcharge_pct": 10},
            {"name": "Bui", "capital": "Kumbo", "transport_index": 1.20, "logistics_difficulty": "high", "surcharge_pct": 9},
            {"name": "Donga-Mantung", "capital": "Nkambé", "transport_index": 1.22, "logistics_difficulty": "high", "surcharge_pct": 10},
            {"name": "Menchum", "capital": "Wum", "transport_index": 1.24, "logistics_difficulty": "high", "surcharge_pct": 11},
            {"name": "Momo", "capital": "Mbengwi", "transport_index": 1.22, "logistics_difficulty": "high", "surcharge_pct": 10},
            {"name": "Ngo-Ketunjia", "capital": "Ndop", "transport_index": 1.20, "logistics_difficulty": "high", "surcharge_pct": 9},
        ],
    },
    {
        "name": "South",
        "name_fr": "Sud",
        "capital": "Ebolowa",
        "soil_type": "Ferralitic / Clay-sandy",
        "hazard_count": 2,
        "foundation": "Standard strip or raft depending on soil test",
        "climate_tip": "Equatorial rainforest climate with heavy rainfall. Elevated foundation and good drainage essential.",
        "divisions": [
            {"name": "Mvila", "capital": "Ebolowa", "transport_index": 1.12, "logistics_difficulty": "moderate", "surcharge_pct": 5},
            {"name": "Dja-et-Lobo", "capital": "Sangmélima", "transport_index": 1.16, "logistics_difficulty": "moderate", "surcharge_pct": 7},
            {"name": "Océan", "capital": "Kribi", "transport_index": 1.08, "logistics_difficulty": "low", "surcharge_pct": 3},
            {"name": "Vallée-du-Ntem", "capital": "Ambam", "transport_index": 1.18, "logistics_difficulty": "moderate", "surcharge_pct": 8},
        ],
    },
    {
        "name": "East",
        "name_fr": "Est",
        "capital": "Bertoua",
        "soil_type": "Lateritic / Sandy",
        "hazard_count": 2,
        "foundation": "Standard strip footing on lateritic soil",
        "climate_tip": "Equatorial climate with dense forest cover. Good ventilation and anti-mold materials recommended.",
        "divisions": [
            {"name": "Lom-et-Djérem", "capital": "Bertoua", "transport_index": 1.22, "logistics_difficulty": "high", "surcharge_pct": 10},
            {"name": "Boumba-et-Ngoko", "capital": "Yokadouma", "transport_index": 1.35, "logistics_difficulty": "very_high", "surcharge_pct": 18},
            {"name": "Haut-Nyong", "capital": "Abong-Mbang", "transport_index": 1.24, "logistics_difficulty": "high", "surcharge_pct": 11},
            {"name": "Kadey", "capital": "Batouri", "transport_index": 1.28, "logistics_difficulty": "high", "surcharge_pct": 14},
        ],
    },
    {
        "name": "Far North",
        "name_fr": "Extrême-Nord",
        "capital": "Maroua",
        "soil_type": "Sandy / Clay-sandy alluvial",
        "hazard_count": 3,
        "foundation": "Deep strip footing below seasonal water table",
        "climate_tip": "Hot semi-arid Sahel climate with short rainy season. High thermal mass walls, small shaded openings, and cross-ventilation.",
        "divisions": [
            {"name": "Diamaré", "capital": "Maroua", "transport_index": 1.22, "logistics_difficulty": "moderate", "surcharge_pct": 10},
            {"name": "Logone-et-Chari", "capital": "Kousséri", "transport_index": 1.28, "logistics_difficulty": "high", "surcharge_pct": 14},
            {"name": "Mayo-Danay", "capital": "Yagoua", "transport_index": 1.26, "logistics_difficulty": "high", "surcharge_pct": 13},
            {"name": "Mayo-Kani", "capital": "Kaélé", "transport_index": 1.26, "logistics_difficulty": "high", "surcharge_pct": 13},
            {"name": "Mayo-Sava", "capital": "Mora", "transport_index": 1.30, "logistics_difficulty": "high", "surcharge_pct": 15},
            {"name": "Mayo-Tsanaga", "capital": "Mokolo", "transport_index": 1.32, "logistics_difficulty": "very_high", "surcharge_pct": 16},
        ],
    },
    {
        "name": "South-West",
        "name_fr": "Sud-Ouest",
        "capital": "Buéa",
        "soil_type": "Volcanic / Coastal sedimentary",
        "hazard_count": 3,
        "foundation": "Elevated foundation for coastal areas, adapted for volcanic slopes",
        "climate_tip": "Coastal tropical with volcanic slopes. Elevated concrete structure, flood-safe ground clearance, and anti-corrosion materials.",
        "divisions": [
            {"name": "Fako", "capital": "Limbe", "transport_index": 1.04, "logistics_difficulty": "low", "surcharge_pct": 1},
            {"name": "Koupé-Manengouba", "capital": "Bangem", "transport_index": 1.16, "logistics_difficulty": "high", "surcharge_pct": 7},
            {"name": "Lebialem", "capital": "Menji", "transport_index": 1.18, "logistics_difficulty": "high", "surcharge_pct": 8},
            {"name": "Manyu", "capital": "Mamfé", "transport_index": 1.18, "logistics_difficulty": "high", "surcharge_pct": 8},
            {"name": "Meme", "capital": "Kumba", "transport_index": 1.10, "logistics_difficulty": "moderate", "surcharge_pct": 4},
            {"name": "Ndian", "capital": "Mundemba", "transport_index": 1.20, "logistics_difficulty": "high", "surcharge_pct": 9},
        ],
    },
]


def get_transport_multiplier(region: str, division: str | None = None) -> float:
    mapped = map_region_name(region)
    loc = get_division_for_location(region)
    actual_region = loc["region_name"]
    actual_division = division or loc["division_name"]
    for r in REGIONS:
        if r["name"] == actual_region:
            for d in r["divisions"]:
                if d["name"] == actual_division:
                    return d["transport_index"]
            avg = sum(d["transport_index"] for d in r["divisions"]) / len(r["divisions"])
            return round(avg, 2)
    return 1.0


def get_location_surcharge_pct(region: str, division: str | None = None) -> int:
    loc = get_division_for_location(region)
    actual_division = division or loc["division_name"]
    for r in REGIONS:
        if r["name"] == loc["region_name"]:
            for d in r["divisions"]:
                if d["name"] == actual_division:
                    return d["surcharge_pct"]
    return 0


REGIONS_BBOX = {
    "Littoral": {"lat_min": 3.3, "lat_max": 5.0, "lng_min": 9.0, "lng_max": 10.5},
    "Centre": {"lat_min": 2.8, "lat_max": 5.5, "lng_min": 10.0, "lng_max": 13.5},
    "West": {"lat_min": 5.0, "lat_max": 6.5, "lng_min": 9.5, "lng_max": 11.0},
    "North": {"lat_min": 7.5, "lat_max": 10.5, "lng_min": 12.0, "lng_max": 15.5},
    "Adamaoua": {"lat_min": 6.0, "lat_max": 8.5, "lng_min": 11.0, "lng_max": 15.5},
    "North-West": {"lat_min": 5.5, "lat_max": 7.5, "lng_min": 9.0, "lng_max": 11.0},
    "South": {"lat_min": 1.5, "lat_max": 4.5, "lng_min": 9.0, "lng_max": 16.5},
    "East": {"lat_min": 2.0, "lat_max": 6.5, "lng_min": 12.5, "lng_max": 16.5},
    "Far North": {"lat_min": 10.0, "lat_max": 13.5, "lng_min": 13.0, "lng_max": 16.0},
    "South-West": {"lat_min": 3.5, "lat_max": 6.5, "lng_min": 8.0, "lng_max": 10.5},
}


def validate_coords_in_region(
    latitude: float,
    longitude: float,
    region: str,
    location_name: str | None = None,
) -> str | None:
    mapped = map_region_name(region)
    bbox = REGIONS_BBOX.get(mapped)
    if not bbox:
        return None
    in_bounds = (
        bbox["lat_min"] <= latitude <= bbox["lat_max"]
        and bbox["lng_min"] <= longitude <= bbox["lng_max"]
    )
    if not in_bounds:
        loc_label = location_name or f"({latitude}, {longitude})"
        nearest = _find_nearest_region(latitude, longitude)
        msg = f"Location '{loc_label}' appears to be outside {mapped} region."
        if nearest:
            msg += f" Coordinates are closer to {nearest}."
        msg += " Please verify the selected region is correct."
        return msg
    return None


def _find_nearest_region(lat: float, lng: float) -> str | None:
    best = None
    best_dist = float("inf")
    for name, hub in SUPPLY_HUBS.items():
        d = (lat - hub["lat"]) ** 2 + (lng - hub["lng"]) ** 2
        if d < best_dist:
            best_dist = d
            best = hub["region"]
    return best
