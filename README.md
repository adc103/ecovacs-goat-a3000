# Ecovacs GOAT A3000 LiDAR - Enhanced Integration

A custom Home Assistant integration that enhances support for the **Ecovacs GOAT A3000 LiDAR** robotic lawn mower (`cr0e4u`).

## What This Fixes

The official `deebot-client` library has several issues with the A3000:

- ❌ Wrong clean command (`clean_V2` instead of `clean`)
- ❌ Wrong state command (`getCleanInfo_V2` instead of `getCleanInfo`)  
- ❌ Incorrect life span components (includes `lensBrush` which doesn't exist on A3000)
- ❌ No map support (position, cached map info, map trace)

## What This Adds

- ✅ Correct `CleanMower` command using `clean` endpoint
- ✅ Correct state tracking via `getCleanInfo`
- ✅ Blade life span only (correct for A3000)
- ✅ Map position tracking
- ✅ Cached map info
- ✅ Map trace

## Installation

1. Install via HACS as a custom repository
2. Add repository URL: `https://github.com/adc103/ecovacs-goat-a3000`
3. Category: **Integration**
4. Install "Ecovacs (GOAT A3000 Enhanced)"
5. Restart Home Assistant
6. The existing Ecovacs integration will be enhanced automatically

## Notes

This is a temporary fix while PRs are submitted to the upstream `deebot-client` library and Home Assistant core.
