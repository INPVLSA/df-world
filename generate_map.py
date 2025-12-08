#!/usr/bin/env python3
"""
DF-World Terrain Map Generator
Generates a terrain map image from region coordinate data.
"""

import sqlite3
from pathlib import Path
from PIL import Image

# Paths
BASE_DIR = Path(__file__).parent
TERRAIN_ICONS_DIR = BASE_DIR / "static" / "icons" / "terrain"
DATA_DIR = BASE_DIR / "data"
WORLDS_DIR = DATA_DIR / "worlds"

# Default tile size (pixels per world tile)
DEFAULT_TILE_SIZE = 16

# Terrain type to filename mapping (lowercase for matching)
TERRAIN_FILES = {
    'ocean': 'ocean.png',
    'lake': 'lake.png',
    'forest': 'forest.png',
    'hills': 'hills.png',
    'mountains': 'mountains.png',
    'grassland': 'grassland.png',
    'desert': 'desert.png',
    'wetland': 'wetland.png',
    'glacier': 'glacier.png',
    'tundra': 'tundra.png',
}

# Fallback colors if sprite not found (RGB)
TERRAIN_COLORS = {
    'ocean': (0, 0, 139),        # Dark blue
    'lake': (65, 105, 225),      # Royal blue
    'forest': (34, 139, 34),     # Forest green
    'hills': (154, 205, 50),     # Yellow green
    'mountains': (139, 137, 137), # Gray
    'grassland': (124, 252, 0),  # Lawn green
    'desert': (238, 214, 175),   # Tan
    'wetland': (85, 107, 47),    # Dark olive green
    'glacier': (240, 248, 255),  # Alice blue
    'tundra': (176, 196, 222),   # Light steel blue
}

DEFAULT_COLOR = (64, 64, 64)  # Dark gray for unknown


def load_terrain_sprites(tile_size):
    """Load and resize terrain sprites. Returns dict of terrain_type -> PIL Image.

    Wiki sprites are 48x32 (3x2 grid of 16x16 tiles). We extract the center-top tile.
    """
    sprites = {}

    for terrain_type, filename in TERRAIN_FILES.items():
        sprite_path = TERRAIN_ICONS_DIR / filename
        if sprite_path.exists():
            try:
                img = Image.open(sprite_path).convert('RGBA')

                # Wiki sprites are 48x32 (3 cols x 2 rows of 16x16 tiles)
                # Extract center-top tile (most representative)
                if img.size == (48, 32):
                    # Crop center-top tile (x=16, y=0, 16x16)
                    img = img.crop((16, 0, 32, 16))

                # Resize to target tile_size if needed
                if img.size != (tile_size, tile_size):
                    img = img.resize((tile_size, tile_size), Image.NEAREST)

                sprites[terrain_type] = img
            except Exception as e:
                print(f"  Warning: Could not load {filename}: {e}")

    return sprites


def create_color_tile(color, tile_size):
    """Create a solid color tile as fallback."""
    img = Image.new('RGBA', (tile_size, tile_size), color + (255,))
    return img


def parse_coords(coords_str):
    """Parse pipe-separated coordinate string into list of (x, y) tuples."""
    if not coords_str:
        return []

    coords = []
    for pair in coords_str.split('|'):
        if ',' in pair:
            try:
                x, y = pair.split(',')
                coords.append((int(x), int(y)))
            except ValueError:
                continue
    return coords


def get_world_bounds(cursor):
    """Determine world dimensions from region coordinates."""
    # Get a sample of coordinates to find bounds
    cursor.execute("SELECT coords FROM regions WHERE coords IS NOT NULL AND coords != '' LIMIT 100")

    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')

    for (coords_str,) in cursor.fetchall():
        for x, y in parse_coords(coords_str):
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

    # If no data found, default to standard DF world size
    if min_x == float('inf'):
        return 0, 0, 128, 128

    return int(min_x), int(min_y), int(max_x), int(max_y)


def generate_terrain_map(db_path, output_path=None, tile_size=DEFAULT_TILE_SIZE):
    """
    Generate terrain map image from world database.

    Args:
        db_path: Path to world SQLite database
        output_path: Output image path (default: same dir as db with _terrain.png suffix)
        tile_size: Pixels per world tile

    Returns:
        Path to generated image, or None on failure
    """
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        return None

    if output_path is None:
        output_path = db_path.with_name(db_path.stem + '_terrain.png')
    else:
        output_path = Path(output_path)

    print(f"Generating terrain map for: {db_path.name}")
    print(f"  Tile size: {tile_size}px")

    # Load sprites
    print("  Loading terrain sprites...")
    sprites = load_terrain_sprites(tile_size)
    print(f"  Loaded {len(sprites)} sprites: {list(sprites.keys())}")

    # Create fallback color tiles for missing sprites
    color_tiles = {}
    for terrain_type, color in TERRAIN_COLORS.items():
        if terrain_type not in sprites:
            color_tiles[terrain_type] = create_color_tile(color, tile_size)

    default_tile = create_color_tile(DEFAULT_COLOR, tile_size)

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get world bounds
    print("  Calculating world bounds...")
    min_x, min_y, max_x, max_y = get_world_bounds(cursor)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    print(f"  World size: {width}x{height} tiles ({min_x},{min_y} to {max_x},{max_y})")

    # Create output image
    img_width = width * tile_size
    img_height = height * tile_size
    print(f"  Output image: {img_width}x{img_height} pixels")

    # Use RGBA for transparency support
    terrain_map = Image.new('RGBA', (img_width, img_height), DEFAULT_COLOR + (255,))

    # Process regions
    print("  Processing regions...")
    cursor.execute("SELECT id, type, coords FROM regions WHERE coords IS NOT NULL AND coords != ''")

    region_count = 0
    tile_count = 0

    for region_id, region_type, coords_str in cursor:
        region_count += 1
        terrain_key = region_type.lower() if region_type else 'unknown'

        # Get sprite or color tile
        tile_img = sprites.get(terrain_key) or color_tiles.get(terrain_key) or default_tile

        # Parse and place tiles
        for x, y in parse_coords(coords_str):
            # Adjust for world offset
            px = (x - min_x) * tile_size
            py = (y - min_y) * tile_size

            # Paste tile
            terrain_map.paste(tile_img, (px, py))
            tile_count += 1

    conn.close()

    print(f"  Processed {region_count} regions, {tile_count} tiles")

    # Save image
    print(f"  Saving to: {output_path}")
    terrain_map.save(output_path, 'PNG', optimize=True)

    # Report file size
    file_size = output_path.stat().st_size
    print(f"  File size: {file_size / 1024:.1f} KB")

    return output_path


def generate_map_for_world(world_id, tile_size=DEFAULT_TILE_SIZE):
    """Generate terrain map for a world by ID."""
    db_path = WORLDS_DIR / f"{world_id}.db"
    output_path = WORLDS_DIR / f"{world_id}_terrain.png"
    return generate_terrain_map(db_path, output_path, tile_size)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: generate_map.py <world_id_or_db_path> [tile_size]")
        print("  world_id_or_db_path: World ID or path to world database")
        print("  tile_size: Pixels per tile (default: 16)")
        sys.exit(1)

    target = sys.argv[1]
    tile_size = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TILE_SIZE

    # Check if it's a path or world ID
    if target.endswith('.db') or '/' in target:
        result = generate_terrain_map(target, tile_size=tile_size)
    else:
        result = generate_map_for_world(target, tile_size=tile_size)

    if result:
        print(f"\nSuccess! Map saved to: {result}")
    else:
        print("\nFailed to generate map.")
        sys.exit(1)
