"""
DMP Container Packing Service
3D Bin Packing API using py3dbp library

Container specifications:
- 20ft: 5.89m x 2.33m x 2.39m (internal), max weight 25,400 kg
- 40ft: 12.19m x 2.44m x 2.59m (internal), max weight 25,400 kg
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from py3dbp import Packer, Bin, Item
import uvicorn

app = FastAPI(
    title="DMP Container Packing Service",
    description="3D Bin Packing API for container loading optimization",
    version="1.0.0"
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
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


class FittedItem(BaseModel):
    """Item that fits in container with position"""
    item_id: int
    name: str
    instance: int  # Instance number (for items with qty > 1)
    position: dict  # x, y, z coordinates
    dimensions: dict  # width, height, depth
    rotation_type: int
    weight_kg: float


class UnfittedItem(BaseModel):
    """Item that doesn't fit"""
    item_id: int
    name: str
    instance: int
    width_cm: float
    height_cm: float
    depth_cm: float
    weight_kg: float
    reason: Optional[str] = None


class PackingResponse(BaseModel):
    """Packing calculation result"""
    success: bool
    container_type: str
    container_dimensions: dict
    total_items_requested: int
    fitted_count: int
    unfitted_count: int
    fitted_items: List[FittedItem]
    unfitted_items: List[UnfittedItem]
    utilization: dict  # CBM and weight utilization percentages
    warnings: List[str]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "dmp-packing-service"}


@app.post("/pack", response_model=PackingResponse)
async def calculate_packing(request: PackingRequest):
    """
    Calculate optimal 3D packing for items in a container

    Uses the py3dbp library which implements the 3D bin packing algorithm.
    Items are packed considering all 6 rotation orientations.
    """
    container_type = request.container_type
    items = request.items

    if container_type not in CONTAINER_SPECS:
        raise HTTPException(status_code=400, detail=f"Invalid container type: {container_type}")

    if not items:
        raise HTTPException(status_code=400, detail="No items provided")

    spec = CONTAINER_SPECS[container_type]
    warnings = []

    # Create packer instance
    packer = Packer()

    # Add the container as a bin
    # py3dbp Bin: name, width, height, depth, max_weight
    container = Bin(
        container_type,
        spec["width"],
        spec["height"],
        spec["depth"],
        spec["max_weight"]
    )
    packer.add_bin(container)

    # Add items to packer
    # Each item with quantity > 1 is added as separate items
    total_items_requested = 0
    for item in items:
        for i in range(item.quantity):
            total_items_requested += 1
            # py3dbp Item: name, width, height, depth, weight
            packer_item = Item(
                f"{item.item_id}_{i}",  # Unique name: item_id + instance
                item.width_cm,
                item.height_cm,
                item.depth_cm,
                item.weight_kg
            )
            packer.add_item(packer_item)

    # Run packing algorithm
    # bigger_first=True prioritizes larger items first (better space utilization)
    # distribute_items=False keeps all items in one bin
    packer.pack(bigger_first=True, distribute_items=False)

    # Process results
    fitted_items = []
    unfitted_items = []
    total_fitted_volume = 0
    total_fitted_weight = 0

    # Get the packed bin (should be only one)
    packed_bin = packer.bins[0]

    # Process fitted items
    for packed_item in packed_bin.items:
        # Parse item_id and instance from name
        parts = packed_item.name.split("_")
        item_id = int(parts[0])
        instance = int(parts[1])

        # Find original item for name
        original_item = next((i for i in items if i.item_id == item_id), None)

        fitted_items.append(FittedItem(
            item_id=item_id,
            name=original_item.name if original_item else "Unknown",
            instance=instance,
            position={
                "x": float(packed_item.position[0]),
                "y": float(packed_item.position[1]),
                "z": float(packed_item.position[2])
            },
            dimensions={
                "width": float(packed_item.width),
                "height": float(packed_item.height),
                "depth": float(packed_item.depth)
            },
            rotation_type=packed_item.rotation_type,
            weight_kg=float(packed_item.weight)
        ))

        # Calculate volume (in cubic cm)
        item_volume = packed_item.width * packed_item.height * packed_item.depth
        total_fitted_volume += item_volume
        total_fitted_weight += packed_item.weight

    # Process unfitted items
    for unfitted_item in packed_bin.unfitted_items:
        parts = unfitted_item.name.split("_")
        item_id = int(parts[0])
        instance = int(parts[1])

        original_item = next((i for i in items if i.item_id == item_id), None)

        unfitted_items.append(UnfittedItem(
            item_id=item_id,
            name=original_item.name if original_item else "Unknown",
            instance=instance,
            width_cm=float(unfitted_item.width),
            height_cm=float(unfitted_item.height),
            depth_cm=float(unfitted_item.depth),
            weight_kg=float(unfitted_item.weight),
            reason="Could not fit in remaining space"
        ))

    # Calculate utilization
    container_volume = spec["width"] * spec["height"] * spec["depth"]
    container_cbm = container_volume / 1000000  # Convert cm³ to m³
    fitted_cbm = total_fitted_volume / 1000000

    utilization = {
        "volume_percent": round((total_fitted_volume / container_volume) * 100, 1),
        "weight_percent": round((total_fitted_weight / spec["max_weight"]) * 100, 1),
        "container_cbm": round(container_cbm, 2),
        "used_cbm": round(fitted_cbm, 2),
        "container_weight_kg": spec["max_weight"],
        "used_weight_kg": round(total_fitted_weight, 2)
    }

    # Add warnings
    if unfitted_items:
        warnings.append(f"{len(unfitted_items)} items could not fit in the container")

    if utilization["weight_percent"] > 95:
        warnings.append("Container is near weight capacity limit")

    return PackingResponse(
        success=len(unfitted_items) == 0,
        container_type=container_type,
        container_dimensions={
            "width_cm": spec["width"],
            "height_cm": spec["height"],
            "depth_cm": spec["depth"],
            "cbm": round(container_cbm, 2)
        },
        total_items_requested=total_items_requested,
        fitted_count=len(fitted_items),
        unfitted_count=len(unfitted_items),
        fitted_items=fitted_items,
        unfitted_items=unfitted_items,
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

    total_cbm = 0
    total_weight = 0
    oversized_items = []

    for item in request.items:
        # Check if individual item is too large for container
        item_fits = (
            (item.width_cm <= spec["width"] and item.height_cm <= spec["height"] and item.depth_cm <= spec["depth"]) or
            (item.width_cm <= spec["width"] and item.height_cm <= spec["depth"] and item.depth_cm <= spec["height"]) or
            (item.width_cm <= spec["height"] and item.height_cm <= spec["width"] and item.depth_cm <= spec["depth"]) or
            (item.width_cm <= spec["height"] and item.height_cm <= spec["depth"] and item.depth_cm <= spec["width"]) or
            (item.width_cm <= spec["depth"] and item.height_cm <= spec["width"] and item.depth_cm <= spec["height"]) or
            (item.width_cm <= spec["depth"] and item.height_cm <= spec["height"] and item.depth_cm <= spec["width"])
        )

        if not item_fits:
            oversized_items.append({
                "item_id": item.item_id,
                "name": item.name,
                "dimensions": f"{item.width_cm} x {item.height_cm} x {item.depth_cm} cm"
            })

        # Calculate totals
        item_volume = (item.width_cm * item.height_cm * item.depth_cm * item.quantity) / 1000000
        total_cbm += item_volume
        total_weight += item.weight_kg * item.quantity

    container_cbm = (spec["width"] * spec["height"] * spec["depth"]) / 1000000

    return {
        "valid": len(oversized_items) == 0 and total_cbm <= container_cbm and total_weight <= spec["max_weight"],
        "total_cbm": round(total_cbm, 2),
        "container_cbm": round(container_cbm, 2),
        "cbm_utilization_percent": round((total_cbm / container_cbm) * 100, 1),
        "total_weight_kg": round(total_weight, 2),
        "max_weight_kg": spec["max_weight"],
        "weight_utilization_percent": round((total_weight / spec["max_weight"]) * 100, 1),
        "oversized_items": oversized_items,
        "warnings": [
            f"Total CBM ({round(total_cbm, 2)}) exceeds container capacity ({round(container_cbm, 2)})" if total_cbm > container_cbm else None,
            f"Total weight ({round(total_weight, 2)} kg) exceeds limit ({spec['max_weight']} kg)" if total_weight > spec["max_weight"] else None,
            f"{len(oversized_items)} items are too large for container" if oversized_items else None
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
