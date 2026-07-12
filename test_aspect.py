import os
import sys
from datetime import datetime, timedelta
import swisseph as swe

# Ensure ephe path
swe.set_ephe_path(os.path.abspath('../ephe'))

from app import get_positions, compute_aspects

def test():
    # Mock data
    dt_transit_start = datetime(2026, 7, 12, 4, 30) # UTC
    lat, lon = 18.5204, 73.8567
    
    # Get natal mock (just use the same for simplicity)
    natal_pos, _ = get_positions(dt_transit_start, lat, lon)
    
    # Run aspect engine for As
    aspects = compute_aspects(dt_transit_start, lat, lon, natal_pos, hours=24, selected_planets=["As"])
    
    for a in aspects:
        print(f"{a['time']} | {a['transit_planet']} -> {a['natal_planet']} | {a['aspect_name']} {a['aspect_deg']}")
        
if __name__ == '__main__':
    test()
