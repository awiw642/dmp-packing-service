"""
DMP Container Packing Service
Fast 3D Bin Packing API using mathematical stacking

Container specifications:
- 20ft: 5.89m x 2.33m x 2.39m (internal), max weight 25,400 kg
- 40ft: 12.19m x 2.44m x 2.59m (internal), max weight 25,400 kg
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
import uvicorn
import math

app = FastAPI(
    title="DMP Container Packing Service",
    description="3D Bin Packing API for container loading optimization",
    version="2.0.0"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Container specifications (internal dimensions in cm, weight in kg)
CONTAINER_SPECS = {
    "20ft": {
        "width": 589,      # 5.89m in cm
        "height": 239,     # 2.39m in cm
        "depth": 233,      # 2.33m in cm
        "max_weight": 25400  # kg
    },
    "40ft": {
        "width": 1219,     # 12.19m in cm
        "height": 259,     # 2.59m in cm
        "depth": 244,      # 2.44m in cm
        "max_weight": 25400  # kg
    }
}


# Request/Response Models
class PackingItem(BaseModel):
    """Item to be packed"""
    item_id: int
    name: str
    quantity: int = Field(ge=1)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    depth_cm: float = Field(gt=0)
    weight_kg: float = Field(ge=0)


class PackingRequest(BaseModel):
    """Request to calculate packing"""
    container_type: str = Field(pattern="^(20ft|40ft)$")
    items: List[PackingItem]


class PackingItemResult(BaseModel):
    """Result for each item type"""
    item_id: int
    name: str
    requested: int
    fitted: int
    unfitted: int
    dimensions_cm: str
    best_orientation: str
    items_per_layer: int
    layers: int
    max_fit_by_volume: int
    max_fit_by_weight: int
    weight_kg_total: float
    cbm_total: float


class PackingResponse(BaseModel):
    """Packing calculation result"""
    success: bool
    container_type: str
    container_dimensions: dict
    total_items_requested: int
    fitted_count: int
    unfitted_count: int
    items_breakdown: List[PackingItemResult]
    utilization: dict
    warnings: List[str]


def calculate_max_fit_for_orientation(
    item_w: float, item_h: float, item_d: float,
    cont_w: float, cont_h: float, cont_d: float
) -> Tuple[int, int, int, int]:
    """
    Calculate how many items fit in a specific orientation.
    Returns (items_x, items_y, items_z, total)
    """
    if item_w > cont_w or item_h > cont_h or item_d > cont_d:
        return (0, 0, 0, 0)

    items_x = int(cont_w // item_w)  # Along width
    items_y = int(cont_h // item_h)  # Along height
    items_z = int(cont_d // item_d)  # Along depth

    return (items_x, items_y, items_z, items_x * items_y * items_z)


def find_best_orientation(
    w: float, h: float, d: float,
    cont_w: float, cont_h: float, cont_d: float
) -> Tuple[int, str, int, int]:
    """
    Try all 6 orientations and find the one that fits most items.
    Returns (max_items, orientation_name, items_per_layer, layers)
    """
    orientations = [
        ((w, h, d), "W×H×D (original)"),
        ((w, d, h), "W×D×H"),
        ((h, w, d), "H×W×D"),
        ((h, d, w), "H×D×W"),
        ((d, w, h), "D×W×H"),
        ((d, h, w), "D×H×W"),
    ]

    best = (0, "none", 0, 0)

    for (iw, ih, id), name in orientations:
        items_x, items_y, items_z, total = calculate_max_fit_for_orientation(
            iw, ih, id, cont_w, cont_h, cont_d
        )
        if total > best[0]:
            items_per_layer = items_x * items_z  # Items in one horizontal layer
            layers = items_y  # Number of layers stacked vertically
            best = (total, name, items_per_layer, layers)

    return best


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "dmp-packing-service", "version": "2.0.0"}


@app.post("/pack", response_model=PackingResponse)
async def calculate_packing(request: PackingRequest):
    """
    Calculate optimal 3D packing for items in a container.

    Uses mathematical stacking algorithm:
    - Calculates how many items fit based on dimensions
    - Tries all 6 orientations to find best fit
    - Accounts for weight limits
    - Handles large quantities efficiently (O(n) where n = number of product types)
    """
    container_type = request.container_type
    items = request.items

    if container_type not in CONTAINER_SPECS:
        raise HTTPException(status_code=400, detail=f"Invalid container type: {container_type}")

    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    spec = CONTAINER_SPECS[container_type]
    cont_w, cont_h, cont_d = spec["width"], spec["height"], spec["depth"]
    max_weight = spec["max_weight"]
    container_volume = cont_w * cont_h * cont_d
    container_cbm = container_volume / 1000000

    warnings = []
    items_breakdown = []

    total_items_requested = 0
    total_fitted = 0
    total_unfitted = 0
    total_volume_used = 0
    total_weight_used = 0
    remaining_weight_capacity = max_weight

    # Process each item type
    for item in items:
        total_items_requested += item.quantity
        item_volume = item.width_cm * item.height_cm * item.depth_cm
        item_cbm = item_volume / 1000000

        # Find best orientation
        max_fit_volume, orientation, items_per_layer, layers = find_best_orientation(
            item.width_cm, item.height_cm, item.depth_cm,
            cont_w, cont_h, cont_d
        )

        # Check weight constraint
        if item.weight_kg > 0:
            max_fit_weight = int(remaining_weight_capacity // item.weight_kg)
        else:
            max_fit_weight = item.quantity  # No weight limit if item has no weight

        # Actual fit is minimum of volume fit, weight fit, and requested
        max_fit = min(max_fit_volume, max_fit_weight)
        fitted = min(max_fit, item.quantity)
        unfitted = item.quantity - fitted

        # Update totals
        total_fitted += fitted
        total_unfitted += unfitted
        total_volume_used += fitted * item_volume
        weight_used = fitted * item.weight_kg
        total_weight_used += weight_used
        remaining_weight_capacity -= weight_used

        items_breakdown.append(PackingItemResult(
            item_id=item.item_id,
            name=item.name,
            requested=item.quantity,
            fitted=fitted,
            unfitted=unfitted,
            dimensions_cm=f"{item.width_cm} × {item.height_cm} × {item.depth_cm}",
            best_orientation=orientation,
            items_per_layer=items_per_layer,
            layers=layers,
            max_fit_by_volume=max_fit_volume,
            max_fit_by_weight=max_fit_weight,
            weight_kg_total=round(weight_used, 2),
            cbm_total=round(fitted * item_cbm, 4)
        ))

        # Add warning if items don't fit
        if unfitted > 0:
            if max_fit_volume == 0:
                warnings.append(f"{item.name}: Item is too large for container in any orientation")
            elif max_fit_weight < item.quantity and max_fit_weight < max_fit_volume:
                warnings.append(f"{item.name}: {unfitted} items don't fit (weight limit)")
            else:
                warnings.append(f"{item.name}: {unfitted} items don't fit (space limit)")

    # Calculate utilization
    used_cbm = total_volume_used / 1000000
    volume_percent = (total_volume_used / container_volume) * 100
    weight_percent = (total_weight_used / max_weight) * 100

    utilization = {
        "volume_percent": round(volume_percent, 1),
        "weight_percent": round(weight_percent, 1),
        "container_cbm": round(container_cbm, 2),
        "used_cbm": round(used_cbm, 4),
        "remaining_cbm": round(container_cbm - used_cbm, 4),
        "container_weight_kg": max_weight,
        "used_weight_kg": round(total_weight_used, 2),
        "remaining_weight_kg": round(max_weight - total_weight_used, 2)
    }

    # Add general warnings
    if weight_percent > 95:
        warnings.append("Container is near weight capacity limit")

    if volume_percent > 95:
        warnings.append("Container is near volume capacity limit")

    return PackingResponse(
        success=total_unfitted == 0,
        container_type=container_type,
        container_dimensions={
            "width_cm": spec["width"],
            "height_cm": spec["height"],
            "depth_cm": spec["depth"],
            "cbm": round(container_cbm, 2)
        },
        total_items_requested=total_items_requested,
        fitted_count=total_fitted,
        unfitted_count=total_unfitted,
        items_breakdown=items_breakdown,
        utilization=utilization,
        warnings=warnings
    )


@app.post("/validate")
async def validate_items(request: PackingRequest):
    """
    Quick validation to check if items can potentially fit
    without running full packing algorithm
    """
    spec = CONTAINER_SPECS[request.container_type]
    cont_w, cont_h, cont_d = spec["width"], spec["height"], spec["depth"]

    total_cbm = 0
    total_weight = 0
    oversized_items = []

    for item in request.items:
        # Check if individual item fits in any orientation
        max_fit, _, _, _ = find_best_orientation(
            item.width_cm, item.height_cm, item.depth_cm,
            cont_w, cont_h, cont_d
        )

        if max_fit == 0:
            oversized_items.append({
                "item_id": item.item_id,
                "name": item.name,
                "dimensions": f"{item.width_cm} × {item.height_cm} × {item.depth_cm} cm"
            })

        # Calculate totals
        item_volume = (item.width_cm * item.height_cm * item.depth_cm * item.quantity) / 1000000
        total_cbm += item_volume
        total_weight += item.weight_kg * item.quantity

    container_cbm = (spec["width"] * spec["height"] * spec["depth"]) / 1000000

    warnings_list = []
    if total_cbm > container_cbm:
        warnings_list.append(f"Total CBM ({round(total_cbm, 2)}) exceeds container capacity ({round(container_cbm, 2)})")
    if total_weight > spec["max_weight"]:
        warnings_list.append(f"Total weight ({round(total_weight, 2)} kg) exceeds limit ({spec['max_weight']} kg)")
    if oversized_items:
        warnings_list.append(f"{len(oversized_items)} items are too large for container")

    return {
        "valid": len(oversized_items) == 0 and total_cbm <= container_cbm and total_weight <= spec["max_weight"],
        "total_cbm": round(total_cbm, 4),
        "container_cbm": round(container_cbm, 2),
        "cbm_utilization_percent": round((total_cbm / container_cbm) * 100, 1),
        "total_weight_kg": round(total_weight, 2),
        "max_weight_kg": spec["max_weight"],
        "weight_utilization_percent": round((total_weight / spec["max_weight"]) * 100, 1),
        "oversized_items": oversized_items,
        "warnings": warnings_list
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
