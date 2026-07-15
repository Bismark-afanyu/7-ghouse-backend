from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LabelItem:
    en: str
    fr: str
    x_ratio: float
    y_ratio: float
    anchor: str = "lt"
    font_size_ratio: float = 0.028


@dataclass
class ViewLabelConfig:
    labels: list[LabelItem] = field(default_factory=list)
    legend_labels: list[tuple[str, str]] = field(default_factory=list)
    show_title_banner: bool = False
    title_en: str = ""
    title_fr: str = ""
    show_legend: bool = False


VIEW_LABEL_CONFIGS: dict[str, ViewLabelConfig] = {
    "floor_plans_composite": ViewLabelConfig(
        show_title_banner=True,
        title_en="Floor Plans",
        title_fr="Plans d'étage",
        show_legend=False,
    ),
    "elevations_composite": ViewLabelConfig(
        labels=[
            LabelItem("Front Elevation", "Élévation avant", 0.25, 0.47, "cb"),
            LabelItem("Rear Elevation", "Élévation arrière", 0.75, 0.47, "cb"),
            LabelItem("Left Elevation", "Élévation gauche", 0.25, 0.97, "cb"),
            LabelItem("Right Elevation", "Élévation droite", 0.75, 0.97, "cb"),
        ],
    ),
    "exterior_3d_composite": ViewLabelConfig(
        labels=[
            LabelItem("Front View", "Vue avant", 0.03, 0.03, "lt"),
            LabelItem("Rear View", "Vue arrière", 0.53, 0.03, "lt"),
        ],
    ),
    "interior_living_composite": ViewLabelConfig(
        labels=[
            LabelItem("Living Room", "Salon", 0.03, 0.03, "lt"),
            LabelItem("Kitchen & Dining", "Cuisine & Salle à manger", 0.53, 0.03, "lt"),
        ],
    ),
    "master_suite_composite": ViewLabelConfig(
        labels=[
            LabelItem("Master Bedroom", "Chambre principale", 0.03, 0.03, "lt"),
            LabelItem("Luxury Bathroom", "Salle de bain de luxe", 0.53, 0.03, "lt"),
        ],
    ),
    "topdown_3d_view": ViewLabelConfig(
        show_title_banner=True,
        title_en="Top-Down View",
        title_fr="Vue aérienne",
        show_legend=False,
    ),
    "topdown_3d_ground_floor": ViewLabelConfig(
        show_title_banner=True,
        title_en="Ground Floor",
        title_fr="Rez-de-chaussée",
        show_legend=False,
    ),
    "topdown_3d_upper_floor": ViewLabelConfig(
        show_title_banner=True,
        title_en="Upper Floor",
        title_fr="Étage supérieur",
        show_legend=False,
    ),
    "measurements_table": ViewLabelConfig(
        show_title_banner=True,
        title_en="Room Measurements",
        title_fr="Plan des chambres",
        show_legend=False,
    ),
    "floor_plan_main": ViewLabelConfig(
        labels=[
            LabelItem("Floor Plan", "Plan d'étage", 0.50, 0.03, "ct"),
        ],
    ),
    "floor_plan_annotated": ViewLabelConfig(
        labels=[
            LabelItem("Annotated Plan", "Plan annoté", 0.50, 0.03, "ct"),
        ],
    ),
    "floor_plan_3d": ViewLabelConfig(
        labels=[
            LabelItem("3D Isometric", "Isométrique 3D", 0.50, 0.03, "ct"),
        ],
    ),
}


def get_label_config(view_type: str) -> ViewLabelConfig:
    return VIEW_LABEL_CONFIGS.get(view_type, ViewLabelConfig())


def get_default_legend_labels(
    num_bedrooms: int = 3,
    num_bathrooms: float = 2.0,
    kitchen_type: str = "Open",
    key_rooms: Optional[list[str]] = None,
    outdoor_spaces: Optional[list[str]] = None,
) -> list[tuple[str, str]]:
    labels: list[tuple[str, str]] = [
        ("Living Room", "Salon"),
        ("Kitchen", "Cuisine"),
        ("Dining", "Salle à manger"),
        ("Master Bedroom", "Chambre principale"),
    ]

    extra_bedrooms = max(0, num_bedrooms - 1)
    for i in range(extra_bedrooms):
        labels.append((f"Bedroom {i+2}", f"Chambre {i+2}"))

    for _ in range(int(num_bathrooms)):
        labels.append(("Bathroom", "Salle de bain"))

    if key_rooms:
        room_map = {
            "home office": ("Home Office", "Bureau"),
            "media room": ("Media Room", "Salle média"),
            "playroom": ("Playroom", "Salle de jeux"),
            "gym": ("Gym", "Gymnase"),
            "laundry": ("Laundry", "Buanderie"),
            "pantry": ("Pantry", "Garde-manger"),
            "library": ("Library", "Bibliothèque"),
            "guest room": ("Guest Room", "Chambre d'amis"),
        }
        for room in key_rooms:
            mapped = room_map.get(room.lower().strip(), (room.title(), room.title()))
            labels.append(mapped)

    if outdoor_spaces:
        space_map = {
            "porch": ("Porch", "Véranda"),
            "patio": ("Patio", "Patio"),
            "deck": ("Deck", "Terrasse"),
            "balcony": ("Balcony", "Balcon"),
            "courtyard": ("Courtyard", "Cour"),
            "breezeway": ("Breezeway", "Avant-corps"),
            "outdoor kitchen": ("Outdoor Kitchen", "Cuisine extérieure"),
        }
        for space in outdoor_spaces:
            mapped = space_map.get(space.lower().strip(), (space.title(), space.title()))
            labels.append(mapped)

    return labels
