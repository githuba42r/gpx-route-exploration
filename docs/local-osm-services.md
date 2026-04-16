# Running Valhalla and Nominatim Locally

This guide explains how to set up local Valhalla (routing + elevation) and Nominatim (geocoding) services using Docker, including how to create smaller regional extracts for faster setup and lower disk usage.

## Overview

The GPX Gradient Analysis tool depends on two OpenStreetMap-based services:

| Service | Purpose | Docker Image |
|---------|---------|-------------|
| **Valhalla** | Routing engine + DEM elevation data (terrain gradient feature) | `ghcr.io/valhalla/valhalla:latest` |
| **Nominatim** | Geocoding (place name → coordinates) | `mediagis/nominatim:4.4` |

Both can also be used as public services (see [Public Services](#public-services) below), but local instances offer better performance, privacy, and no rate limits.

## Quick Setup (Full Region)

### Directory Structure

```
osm-services/
  valhalla/
    custom_files/        # OSM data + generated tiles
  nominatim/
    data/                # OSM extracts
  docker-compose.yml
```

### docker-compose.yml

```yaml
services:
  valhalla:
    image: ghcr.io/valhalla/valhalla:latest
    container_name: valhalla
    ports:
      - "8002:8002"
    volumes:
      - ./valhalla/custom_files:/custom_files
    environment:
      - tile_urls=http://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf
      - serve_tiles=True
      - build_elevation=True
      - build_admins=True
      - build_time_zones=True
      - force_rebuild=False
    restart: unless-stopped

  nominatim:
    image: mediagis/nominatim:4.4
    container_name: nominatim
    ports:
      - "8001:8080"
    volumes:
      - nominatim-data:/var/lib/postgresql/14/main
      - ./nominatim/data:/data
    environment:
      - PBF_PATH=/data/australia-latest.osm.pbf
      - REPLICATION_URL=https://download.geofabrik.de/australia-oceania/australia-updates/
    shm_size: 1g
    restart: unless-stopped

volumes:
  nominatim-data:
```

### First Run

```bash
mkdir -p valhalla/custom_files nominatim/data

# Download the OSM extract (Australia example — ~1.1 GB)
wget -P nominatim/data https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf

docker compose up -d
```

Valhalla will build routing tiles on first start (can take 30-60 minutes for Australia). Nominatim will import the data into PostgreSQL (can take several hours for a country-level extract).

## Smaller Regional Extracts

For faster setup and less disk space, you can clip the OSM data to just the region you need.

### Install osmium-tool

```bash
# Arch Linux
sudo pacman -S osmium-tool

# Ubuntu/Debian
sudo apt install osmium-tool

# macOS
brew install osmium-tool
```

### Download and Clip

Example: South-East Queensland (Toowoomba to Gold Coast to Noosa):

```bash
cd nominatim/data

# Download the state extract (~200 MB)
wget https://download.openstreetmap.fr/extracts/oceania/australia/queensland-latest.osm.pbf

# Clip to a bounding box (West, South, East, North)
# This covers Toowoomba → Gold Coast → Noosa
osmium extract \
  --bbox 151.8,-28.4,153.6,-26.4 \
  --strategy complete_ways \
  -o se-qld-latest.osm.pbf \
  queensland-latest.osm.pbf

# Optional: remove the full state file to save space
rm queensland-latest.osm.pbf
```

The clipped file will be ~30-50 MB instead of ~200 MB, and imports in minutes instead of hours.

### Common Bounding Boxes

| Region | Bbox (W,S,E,N) | Approx Size |
|--------|----------------|-------------|
| SE Queensland | `151.8,-28.4,153.6,-26.4` | ~30-50 MB |
| Sydney Metro | `150.5,-34.2,151.5,-33.4` | ~40-60 MB |
| Melbourne Metro | `144.5,-38.1,145.5,-37.5` | ~30-50 MB |
| Greater Brisbane | `152.6,-27.8,153.4,-27.0` | ~15-25 MB |

### Using the Clipped Extract

Update the `docker-compose.yml` to reference the clipped file:

```yaml
# Nominatim
environment:
  - PBF_PATH=/data/se-qld-latest.osm.pbf

# Valhalla — use a file URL instead of a download URL
environment:
  - tile_urls=file:///custom_files/se-qld-latest.osm.pbf
```

For Valhalla, copy the clipped file into the Valhalla data directory:

```bash
cp nominatim/data/se-qld-latest.osm.pbf valhalla/custom_files/
```

### Elevation Data (Valhalla DEM)

Valhalla's terrain gradient feature requires DEM (Digital Elevation Model) data. With `build_elevation=True`, Valhalla downloads SRTM tiles automatically for the region covered by the OSM data. This adds ~500 MB for a country but only ~50 MB for a regional extract.

If the DEM data is not available for a region, the terrain gradient feature will return null elevations. The route-based gradient analysis (from GPX elevation data) still works without DEM.

## Public Services

If you don't want to run local services, you can use public instances. However, these have rate limits and may be slower:

### Public Nominatim

The OpenStreetMap project runs a public Nominatim instance:

```
NOMINATIM_URL=https://nominatim.openstreetmap.org
```

**Usage policy:** Max 1 request/second, no bulk queries. See [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/).

### Public Valhalla

There is no official public Valhalla instance. Options:

1. **Run your own** (recommended) — see setup above
2. **Hosted services** — some providers offer hosted Valhalla APIs (e.g., Mapbox, Stadiamaps) but may require API keys and have different endpoints

**Note:** The terrain gradient feature specifically requires Valhalla's `/height` endpoint with DEM data loaded, which most hosted services do not provide. For this feature, a local Valhalla instance with `build_elevation=True` is required.

## Verifying Your Setup

Once the services are running, verify them:

```bash
# Check Nominatim
curl http://localhost:8001/status
# Expected: "OK"

# Check Valhalla
curl http://localhost:8002/status
# Expected: JSON with version and available actions

# Test Valhalla height (DEM)
curl -s http://localhost:8002/height \
  -d '{"shape":[{"lat":-27.47,"lon":152.93}]}' | python3 -m json.tool
# Expected: {"shape":[...],"height":[<number>]}
# If height is null, DEM data hasn't been built yet
```

## Disk Space Summary

| Setup | Nominatim | Valhalla (tiles + DEM) | Total |
|-------|-----------|----------------------|-------|
| Full Australia | ~15 GB | ~3 GB | ~18 GB |
| Queensland state | ~3 GB | ~800 MB | ~4 GB |
| SE QLD (clipped) | ~500 MB | ~200 MB | ~700 MB |
| Greater Brisbane | ~300 MB | ~100 MB | ~400 MB |

Regional extracts are the recommended approach for development and personal use.
