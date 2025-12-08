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

# Terrain types
TERRAIN_TYPES = [
    'ocean', 'lake', 'forest', 'hills', 'mountains',
    'grassland', 'desert', 'wetland', 'glacier', 'tundra'
]

# Evilness variants
EVILNESS_VARIANTS = ['neutral', 'good', 'evil']

# Overlay terrains - these need a base terrain underneath
OVERLAY_TERRAINS = {'forest'}
OVERLAY_BASE_TERRAIN = 'grassland'

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

# Color tints for evilness (applied to fallback colors)
EVILNESS_TINTS = {
    'neutral': (1.0, 1.0, 1.0),
    'good': (0.8, 1.0, 0.8),    # Greenish tint
    'evil': (1.0, 0.7, 0.7),    # Reddish tint
}

DEFAULT_COLOR = (64, 64, 64)  # Dark gray for unknown


def load_sprite(sprite_path, tile_size, fit_full=False):
    """Load and process a single sprite file.

    Args:
        sprite_path: Path to sprite file
        tile_size: Target tile size in pixels
        fit_full: If True, scale entire sprite to fit tile. If False, extract center tile.
    """
    if not sprite_path.exists():
        return None

    try:
        img = Image.open(sprite_path).convert('RGBA')

        # Wiki sprites are 48x32 (3 cols x 2 rows of 16x16 tiles)
        if img.size == (48, 32):
            if fit_full:
                # Scale the full sprite to fit within tile_size
                # Keep aspect ratio, fit within tile
                img = img.resize((tile_size, int(tile_size * 32 / 48)), Image.NEAREST)
                # Create a tile-sized image and paste centered
                result = Image.new('RGBA', (tile_size, tile_size), (0, 0, 0, 0))
                y_offset = (tile_size - img.height) // 2
                result.paste(img, (0, y_offset), img)
                img = result
            else:
                # Extract center-top tile (most representative)
                img = img.crop((16, 0, 32, 16))
                if img.size != (tile_size, tile_size):
                    img = img.resize((tile_size, tile_size), Image.NEAREST)
        elif img.size != (tile_size, tile_size):
            # Resize to target tile_size if needed
            img = img.resize((tile_size, tile_size), Image.NEAREST)

        return img
    except Exception as e:
        print(f"  Warning: Could not load {sprite_path.name}: {e}")
        return None


def load_terrain_sprites(tile_size):
    """Load all terrain sprites with evilness variants.

    Returns dict of (terrain_type, evilness) -> PIL Image.
    """
    sprites = {}

    for terrain in TERRAIN_TYPES:
        for evilness in EVILNESS_VARIANTS:
            # Determine filename
            if evilness == 'neutral':
                filename = f"{terrain}.png"
            else:
                filename = f"{terrain}_{evilness}.png"

            sprite_path = TERRAIN_ICONS_DIR / filename
            # Use fit_full for overlay terrains to show full sprite
            fit_full = terrain in OVERLAY_TERRAINS
            img = load_sprite(sprite_path, tile_size, fit_full=fit_full)

            if img:
                sprites[(terrain, evilness)] = img

    return sprites


def create_color_tile(color, tile_size):
    """Create a solid color tile as fallback."""
    img = Image.new('RGBA', (tile_size, tile_size), color + (255,))
    return img


def get_fallback_tile(terrain_type, evilness, tile_size, fallback_cache):
    """Get or create a fallback color tile for terrain/evilness combo."""
    cache_key = (terrain_type, evilness)
    if cache_key in fallback_cache:
        return fallback_cache[cache_key]

    base_color = TERRAIN_COLORS.get(terrain_type, DEFAULT_COLOR)
    tint = EVILNESS_TINTS.get(evilness, (1.0, 1.0, 1.0))

    # Apply tint
    color = tuple(int(c * t) for c, t in zip(base_color, tint))

    tile = create_color_tile(color, tile_size)
    fallback_cache[cache_key] = tile
    return tile


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

    # Load sprites with evilness variants
    print("  Loading terrain sprites...")
    sprites = load_terrain_sprites(tile_size)
    print(f"  Loaded {len(sprites)} sprite variants")

    # Fallback cache for missing sprites
    fallback_cache = {}
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

    # Process regions - now including evilness
    print("  Processing regions...")
    cursor.execute("""
        SELECT id, type, coords, evilness
        FROM regions
        WHERE coords IS NOT NULL AND coords != ''
    """)

    region_count = 0
    tile_count = 0
    evilness_stats = {'good': 0, 'neutral': 0, 'evil': 0, 'unknown': 0}

    for region_id, region_type, coords_str, evilness in cursor:
        region_count += 1
        terrain_key = region_type.lower() if region_type else 'unknown'
        evilness_key = evilness.lower() if evilness else 'neutral'

        # Track evilness stats
        if evilness_key in evilness_stats:
            evilness_stats[evilness_key] += 1
        else:
            evilness_stats['unknown'] += 1

        # Get sprite for this terrain/evilness combo
        sprite_key = (terrain_key, evilness_key)
        tile_img = sprites.get(sprite_key)

        # Try neutral variant as fallback
        if not tile_img:
            tile_img = sprites.get((terrain_key, 'neutral'))

        # Use color fallback if no sprite
        if not tile_img:
            tile_img = get_fallback_tile(terrain_key, evilness_key, tile_size, fallback_cache)

        # For overlay terrains (like forest), get base terrain tile
        base_tile = None
        if terrain_key in OVERLAY_TERRAINS:
            base_key = (OVERLAY_BASE_TERRAIN, evilness_key)
            base_tile = sprites.get(base_key)
            if not base_tile:
                base_tile = sprites.get((OVERLAY_BASE_TERRAIN, 'neutral'))
            if not base_tile:
                base_tile = get_fallback_tile(OVERLAY_BASE_TERRAIN, evilness_key, tile_size, fallback_cache)

        # Parse and place tiles
        for x, y in parse_coords(coords_str):
            px = (x - min_x) * tile_size
            py = (y - min_y) * tile_size

            # For overlay terrains, first paste base, then composite overlay
            if base_tile:
                terrain_map.paste(base_tile, (px, py))
                terrain_map.paste(tile_img, (px, py), tile_img)  # Use alpha mask
            else:
                terrain_map.paste(tile_img, (px, py))
            tile_count += 1

    conn.close()

    print(f"  Processed {region_count} regions, {tile_count} tiles")
    print(f"  Evilness breakdown: {evilness_stats}")

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
