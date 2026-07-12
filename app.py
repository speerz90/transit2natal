from flask import Flask, render_template, request, jsonify
import swisseph as swe
import os
from datetime import datetime, timedelta
import math

app = Flask(__name__, template_folder="templates")

# ====================== SWISS EPHEMERIS ======================
EPHE_DIR = os.path.join(os.path.dirname(__file__), "ephe")
swe.set_ephe_path(os.path.abspath(EPHE_DIR))
swe.set_sid_mode(swe.SIDM_LAHIRI)

SIGNS = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]
SIGN_FULL = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
             "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

# Planet IDs — includes outer planets
PLANETS = {
    "Su": swe.SUN,
    "Mo": swe.MOON,
    "Me": swe.MERCURY,
    "Ve": swe.VENUS,
    "Ma": swe.MARS,
    "Ju": swe.JUPITER,
    "Sa": swe.SATURN,
    "Ra": swe.TRUE_NODE,
    "Ur": swe.URANUS,
    "Ne": swe.NEPTUNE,
    "Pl": swe.PLUTO,
}


def get_ayanamsa(jd):
    """Get current ayanamsa value."""
    return swe.get_ayanamsa_ut(jd)


def is_retrograde(jd, planet_id):
    """Check if planet is retrograde at given Julian day."""
    if planet_id == swe.SUN or planet_id == swe.MOON:
        return False
    result = swe.calc_ut(jd, planet_id, swe.FLG_SIDEREAL | swe.FLG_SPEED)
    speed = result[0][3]  # daily speed in longitude
    return speed < 0


def is_combust(sun_lon, planet_lon, planet_key):
    """Check if a planet is combust (too close to Sun)."""
    if planet_key in ("Su", "Ra", "Ke"):
        return False
    diff = abs(sun_lon - planet_lon) % 360
    dist = min(diff, 360 - diff)
    combust_orbs = {
        "Mo": 12, "Me": 14, "Ve": 10, "Ma": 17,
        "Ju": 11, "Sa": 15, "Ur": 0, "Ne": 0, "Pl": 0
    }
    orb = combust_orbs.get(planet_key, 0)
    return dist <= orb if orb > 0 else False


def compute_fortuna(asc_lon, sun_lon, moon_lon, is_day_chart):
    """Compute Part of Fortune longitude."""
    if is_day_chart:
        fortuna = asc_lon + moon_lon - sun_lon
    else:
        fortuna = asc_lon + sun_lon - moon_lon
    return fortuna % 360


def compute_aspects(dt_transit_start, transit_lat, transit_lon, natal_pos, hours=48, selected_planets=None, selected_aspects=None):
    if selected_planets is None:
        selected_planets = ["Mo", "Su", "Me", "Ve", "Ma"]
    moving_planets = selected_planets

    natal_points = {k: v["longitude"] for k, v in natal_pos.items() if k != "For"}

    # Build aspects_to_check from selected_aspects
    all_aspects = {
        "Conjunction": {0: "Conjunction"},
        "Sextile": {60: "Sextile", 300: "Sextile"},
        "Square": {90: "Square", 270: "Square"},
        "Trine": {120: "Trine", 240: "Trine"},
        "Opposition": {180: "Opposition"},
    }
    if selected_aspects is None:
        selected_aspects = ["Conjunction", "Square", "Trine", "Opposition"]

    aspects_to_check = {}
    for asp_name in selected_aspects:
        if asp_name in all_aspects:
            aspects_to_check.update(all_aspects[asp_name])

    found_aspects = []

    for h in range(hours):
        dt_1 = dt_transit_start + timedelta(hours=h)
        dt_2 = dt_transit_start + timedelta(hours=h+1)

        pos_1, _ = get_positions(dt_1, transit_lat, transit_lon)
        pos_2, _ = get_positions(dt_2, transit_lat, transit_lon)

        for tp in moving_planets:
            if tp not in pos_1 or tp not in pos_2:
                continue

            p1_lon = pos_1[tp]["longitude"]
            p2_lon = pos_2[tp]["longitude"]

            # handle wrap-around
            if p2_lon < p1_lon and (p1_lon - p2_lon) > 180:
                p2_lon += 360
            elif p1_lon < p2_lon and (p2_lon - p1_lon) > 180:
                p1_lon += 360

            for np, n_lon in natal_points.items():
                d1 = p1_lon - n_lon
                d2 = p2_lon - n_lon

                min_d = min(d1, d2)
                max_d = max(d1, d2)

                k_start = int(min_d // 360)

                for k in (k_start, k_start + 1):
                    for asp_deg, asp_name in aspects_to_check.items():
                        target = asp_deg + k * 360
                        if min_d <= target <= max_d:
                            actual_fraction = abs(target - d1) / abs(d2 - d1) if d1 != d2 else 0
                            exact_dt = dt_1 + timedelta(hours=actual_fraction)

                            found_aspects.append({
                                "time": exact_dt.isoformat() + "Z",
                                "transit_planet": tp,
                                "natal_planet": np,
                                "aspect_deg": min(asp_deg, 360 - asp_deg),
                                "aspect_name": asp_name
                            })

    found_aspects.sort(key=lambda x: x["time"])
    return found_aspects


def angular_separation(lon_a, lon_b):
    return abs((lon_a - lon_b + 180) % 360 - 180)


def normalize_delta(delta):
    return (delta + 180) % 360 - 180


def angular_separation(lon_a, lon_b):
    return abs((lon_a - lon_b + 180) % 360 - 180)


def normalize_delta(delta):
    return (delta + 180) % 360 - 180


def compute_transit_aspects(dt_transit_start, transit_lat, transit_lon, hours=48, selected_planets=None, selected_aspects=None, current_orb=3.0):
    if selected_planets is None:
        selected_planets = ["Mo", "Su", "Me", "Ve", "Ma"]

    all_aspects = {
        "Conjunction": {0: "Conjunction"},
        "Sextile": {60: "Sextile", 300: "Sextile"},
        "Square": {90: "Square", 270: "Square"},
        "Trine": {120: "Trine", 240: "Trine"},
        "Opposition": {180: "Opposition"},
    }
    if selected_aspects is None:
        selected_aspects = ["Conjunction", "Square", "Trine", "Opposition"]

    aspects_to_check = {}
    exact_aspects = {}
    for asp_name in selected_aspects:
        if asp_name in all_aspects:
            aspects_to_check.update(all_aspects[asp_name])
            for asp_deg in all_aspects[asp_name]:
                exact_aspects[min(asp_deg, 360 - asp_deg)] = asp_name

    found_aspects = []
    seen = set()

    current_pos, _ = get_positions(dt_transit_start, transit_lat, transit_lon)
    for i, tp in enumerate(selected_planets):
        if tp not in current_pos:
            continue
        for other in selected_planets[i + 1:]:
            if other not in current_pos:
                continue

            sep_now = angular_separation(current_pos[tp]["longitude"], current_pos[other]["longitude"])
            for aspect_deg, aspect_name in exact_aspects.items():
                orb = abs(sep_now - aspect_deg)
                if orb <= current_orb:
                    dedupe_key = ("current", tp, other, aspect_deg)
                    seen.add(dedupe_key)
                    found_aspects.append({
                        "time": dt_transit_start.isoformat() + "Z",
                        "transit_planet": tp,
                        "other_transit_planet": other,
                        "aspect_deg": aspect_deg,
                        "aspect_name": aspect_name,
                        "orb": round(orb, 2),
                        "timing": "Current within 3°",
                        "is_current": True,
                        "separation": round(sep_now, 2)
                    })

    for h in range(hours):
        dt_1 = dt_transit_start + timedelta(hours=h)
        dt_2 = dt_transit_start + timedelta(hours=h + 1)

        pos_1, _ = get_positions(dt_1, transit_lat, transit_lon)
        pos_2, _ = get_positions(dt_2, transit_lat, transit_lon)

        for i, tp in enumerate(selected_planets):
            if tp not in pos_1 or tp not in pos_2:
                continue

            p1_lon = pos_1[tp]["longitude"]
            p2_lon = pos_2[tp]["longitude"]
            if p2_lon < p1_lon and (p1_lon - p2_lon) > 180:
                p2_lon += 360
            elif p1_lon < p2_lon and (p2_lon - p1_lon) > 180:
                p1_lon += 360

            for other in selected_planets[i + 1:]:
                if other not in pos_1 or other not in pos_2:
                    continue

                o1_lon = pos_1[other]["longitude"]
                o2_lon = pos_2[other]["longitude"]
                if o2_lon < o1_lon and (o1_lon - o2_lon) > 180:
                    o2_lon += 360
                elif o1_lon < o2_lon and (o2_lon - o1_lon) > 180:
                    o1_lon += 360

                d1 = normalize_delta(p1_lon - o1_lon)
                d2 = normalize_delta(p2_lon - o2_lon)
                if abs(d2 - d1) > 180:
                    if d2 < d1:
                        d2 += 360
                    else:
                        d1 += 360

                min_d = min(d1, d2)
                max_d = max(d1, d2)
                k_start = int(min_d // 360)

                for k in (k_start - 1, k_start, k_start + 1):
                    for asp_deg, asp_name in aspects_to_check.items():
                        target = asp_deg + k * 360
                        if min_d <= target <= max_d:
                            actual_fraction = abs(target - d1) / abs(d2 - d1) if d1 != d2 else 0
                            exact_dt = dt_1 + timedelta(hours=actual_fraction)
                            aspect_deg = min(asp_deg, 360 - asp_deg)
                            dedupe_key = (exact_dt.replace(second=0, microsecond=0).isoformat(), tp, other, aspect_deg)
                            if dedupe_key in seen:
                                continue
                            seen.add(dedupe_key)

                            found_aspects.append({
                                "time": exact_dt.isoformat() + "Z",
                                "transit_planet": tp,
                                "other_transit_planet": other,
                                "aspect_deg": aspect_deg,
                                "aspect_name": asp_name,
                                "orb": 0,
                                "timing": "Exact upcoming",
                                "is_current": False,
                                "separation": aspect_deg
                            })

    found_aspects.sort(key=lambda x: (not x.get("is_current", False), x["time"], x["transit_planet"], x["other_transit_planet"]))
    return found_aspects


def get_positions(dt, lat=0.0, lon=0.0):
    """Compute all planet positions for a given datetime."""
    jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0 + dt.second / 3600.0)

    positions = {}
    sun_lon = None

    for name, pid in PLANETS.items():
        result = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_SPEED)
        longitude = (result[0][0] - (1.0 / 60.0)) % 360
        sign_idx = int(longitude // 30) % 12
        deg_in_sign = longitude % 30
        retro = is_retrograde(jd, pid)

        if name == "Su":
            sun_lon = longitude

        positions[name] = {
            "longitude": round(longitude, 4),
            "sign_index": sign_idx,
            "sign": SIGNS[sign_idx],
            "sign_full": SIGN_FULL[sign_idx],
            "deg": round(deg_in_sign, 2),
            "deg_min": f"{int(deg_in_sign)}:{int((deg_in_sign % 1) * 60):02d}",
            "retrograde": retro,
            "combust": False,
        }

    # Ketu = opposite of Rahu
    ra_lon = positions["Ra"]["longitude"]
    ke_lon = (ra_lon + 180) % 360
    ke_sign_idx = int(ke_lon // 30) % 12
    ke_deg = ke_lon % 30
    positions["Ke"] = {
        "longitude": round(ke_lon, 4),
        "sign_index": ke_sign_idx,
        "sign": SIGNS[ke_sign_idx],
        "sign_full": SIGN_FULL[ke_sign_idx],
        "deg": round(ke_deg, 2),
        "deg_min": f"{int(ke_deg)}:{int((ke_deg % 1) * 60):02d}",
        "retrograde": positions["Ra"]["retrograde"],
        "combust": False,
    }

    # Mark combust
    if sun_lon is not None:
        for name in positions:
            if name != "Su":
                positions[name]["combust"] = is_combust(
                    sun_lon, positions[name]["longitude"], name
                )

    # Compute Ascendant if lat/lon provided
    asc_lon = None
    if lat != 0 or lon != 0:
        houses = swe.houses_ex(jd, lat, lon, b'P', swe.FLG_SIDEREAL)
        asc_lon = (houses[1][0] - (1.0 / 60.0)) % 360  # Ascendant shifted
        asc_sign_idx = int(asc_lon // 30) % 12
        asc_deg = asc_lon % 30
        positions["As"] = {
            "longitude": round(asc_lon, 4),
            "sign_index": asc_sign_idx,
            "sign": SIGNS[asc_sign_idx],
            "sign_full": SIGN_FULL[asc_sign_idx],
            "deg": round(asc_deg, 2),
            "deg_min": f"{int(asc_deg)}:{int((asc_deg % 1) * 60):02d}",
            "retrograde": False,
            "combust": False,
        }

        # House cusps (all 12)
        house_cusps = []
        for i in range(12):
            h_lon = (houses[0][i] - (1.0 / 60.0)) % 360
            h_sign_idx = int(h_lon // 30) % 12
            h_deg = h_lon % 30
            house_cusps.append({
                "house": i + 1,
                "longitude": round(h_lon, 4),
                "sign_index": h_sign_idx,
                "sign": SIGNS[h_sign_idx],
                "deg_min": f"{int(h_deg)}:{int((h_deg % 1) * 60):02d}",
            })

        return positions, house_cusps

    return positions, []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/compute', methods=['POST'])
def compute():
    data = request.get_json()

    # Natal data
    dob = data.get('dob', '1990-01-22')
    tob = data.get('tob', '17:35')
    utc_offset = float(data.get('utcOffset', 5.5))
    lat = float(data.get('lat', 18.52))
    lon = float(data.get('lon', 73.86))

    # Transit data
    transit_date = data.get('transitDate', '')
    transit_time = data.get('transitTime', '12:00')
    transit_lat = float(data.get('transitLat', lat))
    transit_lon = float(data.get('transitLon', lon))
    aspect_hours = int(data.get('aspectHours', 48))
    selected_planets = data.get('selectedPlanets', ["Mo", "Su", "Me", "Ve", "Ma"])

    try:
        dt_local = datetime.fromisoformat(f"{dob}T{tob}:00")
        dt_natal = dt_local - timedelta(hours=utc_offset)
    except Exception:
        return jsonify({"error": "Invalid natal date/time"}), 400

    natal_pos, house_cusps = get_positions(dt_natal, lat, lon)

    # Transit positions
    transit_pos = {}
    aspects_48h = []
    transit_aspects_48h = []
    if transit_date:
        try:
            dt_transit_local = datetime.fromisoformat(f"{transit_date}T{transit_time}:00")
            dt_transit = dt_transit_local - timedelta(hours=utc_offset)
            transit_pos, _ = get_positions(dt_transit, transit_lat, transit_lon)

            # Compute aspects
            aspects_48h = compute_aspects(
                dt_transit, transit_lat, transit_lon, natal_pos,
                hours=aspect_hours, selected_planets=selected_planets,
                selected_aspects=data.get('selectedAspects', None)
            )
            transit_aspects_48h = compute_transit_aspects(
                dt_transit, transit_lat, transit_lon,
                hours=aspect_hours, selected_planets=selected_planets,
                selected_aspects=data.get('selectedAspects', None)
            )
        except Exception:
            return jsonify({"error": "Invalid transit date/time"}), 400

    return jsonify({
        "natal": natal_pos,
        "transit": transit_pos,
        "houses": house_cusps,
        "aspects_48h": aspects_48h,
        "transit_aspects_48h": transit_aspects_48h,
    })


if __name__ == '__main__':
    app.run(debug=True, port=5001)
