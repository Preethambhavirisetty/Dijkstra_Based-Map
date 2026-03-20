import math
import os
import subprocess
import time
from typing import Dict, List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()


def haversine_meters(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    earth = 6371000
    lat1 = math.radians(a_lat)
    lon1 = math.radians(a_lng)
    lat2 = math.radians(b_lat)
    lon2 = math.radians(b_lng)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * earth * math.asin(math.sqrt(h))


def coord_id(lat: float, lng: float) -> str:
    return f"{lat:.5f},{lng:.5f}"


def edge_cost(distance: float, duration: float) -> float:
    return round(0.4 + distance * 0.0011 + duration * 0.003, 4)


def pick_coords(item: dict):
    candidates = [
        (item.get("location", {}).get("lat"), item.get("location", {}).get("lng")),
        (item.get("location", {}).get("latitude"), item.get("location", {}).get("longitude")),
        (item.get("coordinates", {}).get("lat"), item.get("coordinates", {}).get("lng")),
        (item.get("coordinates", {}).get("latitude"), item.get("coordinates", {}).get("longitude")),
        (item.get("gpsCoordinates", {}).get("latitude"), item.get("gpsCoordinates", {}).get("longitude")),
        (item.get("latitude"), item.get("longitude")),
    ]
    for lat, lng in candidates:
        if lat is None or lng is None:
            continue
        try:
            return {"lat": float(lat), "lng": float(lng)}
        except (TypeError, ValueError):
            continue
    return None


async def resolve_place_with_apify(query: str):
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        return None

    endpoint = os.getenv(
        "APIFY_GOOGLE_PLACES_SYNC_URL",
        "https://api.apify.com/v2/acts/compass~crawler-google-places/run-sync-get-dataset-items",
    )

    if "token=" in endpoint:
        request_url = endpoint
    else:
        joiner = "&" if "?" in endpoint else "?"
        request_url = f"{endpoint}{joiner}token={token}"
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(
            request_url,
            json={
                "searchStringsArray": [query],
                "maxCrawledPlacesPerSearch": 1,
                "language": "en",
                "includeWebResults": False,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Apify place lookup failed.")

    data = response.json()
    first = data[0] if isinstance(data, list) and data else None
    if not first:
        raise HTTPException(status_code=404, detail=f'No place result found for "{query}".')

    coords = pick_coords(first)
    if not coords:
        raise HTTPException(status_code=422, detail=f'Apify returned no coordinates for "{query}".')

    return {
        "query": query,
        "label": first.get("title") or first.get("name") or first.get("address") or query,
        "lat": coords["lat"],
        "lng": coords["lng"],
    }


async def resolve_place_with_nominatim(query: str):
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "pathfinder-local-app/1.0")
    url = "https://nominatim.openstreetmap.org/search"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            params={"format": "json", "limit": 1, "q": query},
            headers={"User-Agent": user_agent},
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Nominatim geocoding failed.")

    data = response.json()
    first = data[0] if isinstance(data, list) and data else None
    if not first:
        raise HTTPException(status_code=404, detail=f'No place found for "{query}".')

    return {
        "query": query,
        "label": first.get("display_name") or query,
        "lat": float(first["lat"]),
        "lng": float(first["lon"]),
    }


async def resolve_place(query: str):
    try:
        apify_result = await resolve_place_with_apify(query)
        if apify_result:
            return apify_result
    except HTTPException:
        # Fallback to keyless geocoding when Apify is unavailable or rate-limited.
        pass
    return await resolve_place_with_nominatim(query)


def build_graph_from_osrm(routes: list):
    node_map = {}
    edges = []
    start_id = None
    end_id = None

    for route in routes:
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                points = step.get("geometry", {}).get("coordinates", [])
                if len(points) < 2:
                    continue

                total_meters = 0.0
                for i in range(len(points) - 1):
                    a = points[i]
                    b = points[i + 1]
                    total_meters += haversine_meters(a[1], a[0], b[1], b[0])
                if total_meters <= 0:
                    continue

                for i in range(len(points) - 1):
                    a = points[i]
                    b = points[i + 1]
                    a_lat, a_lng = a[1], a[0]
                    b_lat, b_lng = b[1], b[0]
                    from_id = coord_id(a_lat, a_lng)
                    to_id = coord_id(b_lat, b_lng)
                    node_map[from_id] = {"id": from_id, "lat": a_lat, "lng": a_lng}
                    node_map[to_id] = {"id": to_id, "lat": b_lat, "lng": b_lng}

                    segment_distance = haversine_meters(a_lat, a_lng, b_lat, b_lng)
                    segment_duration = float(step.get("duration", 0)) * (segment_distance / total_meters)
                    edges.append(
                        {
                            "from": from_id,
                            "to": to_id,
                            "distance": round(segment_distance, 3),
                            "duration": round(segment_duration, 3),
                            "cost": edge_cost(segment_distance, segment_duration),
                            "bidirectional": False,
                        }
                    )

                if start_id is None:
                    start_id = coord_id(points[0][1], points[0][0])
                end_id = coord_id(points[-1][1], points[-1][0])

    return {"nodes": list(node_map.values()), "edges": edges, "start_id": start_id, "end_id": end_id}


def create_edge_lookup(edges: list, directed: bool):
    lookup = {}
    for edge in edges:
        lookup[f'{edge["from"]}->{edge["to"]}'] = edge
        if not directed:
            lookup[f'{edge["to"]}->{edge["from"]}'] = {**edge, "from": edge["to"], "to": edge["from"]}
    return lookup


def summarize_path(path_ids: List[str], node_lookup: Dict[str, dict], edge_lookup: Dict[str, dict]):
    route = []
    distance = 0.0
    duration = 0.0
    cost = 0.0

    for i, node_id in enumerate(path_ids):
        node = node_lookup.get(node_id)
        if node:
            route.append({"lat": node["lat"], "lng": node["lng"]})

        if i < len(path_ids) - 1:
            key = f"{path_ids[i]}->{path_ids[i + 1]}"
            edge = edge_lookup.get(key)
            if edge:
                distance += float(edge.get("distance", 0))
                duration += float(edge.get("duration", 0))
                cost += float(edge.get("cost", 0))

    return {
        "route": route,
        "distance": distance,
        "duration": duration,
        "cost": cost,
        "hops": max(0, len(path_ids) - 1),
    }


def build_detailed_flow(path_ids: List[str], node_lookup: Dict[str, dict], edge_lookup: Dict[str, dict]):
    if len(path_ids) < 2:
        return []

    chunks = []
    seg_index = 1
    acc_distance = 0.0
    acc_duration = 0.0
    chunk_start = path_ids[0]
    last_to = path_ids[0]

    for i in range(len(path_ids) - 1):
        from_id = path_ids[i]
        to_id = path_ids[i + 1]
        key = f"{from_id}->{to_id}"
        edge = edge_lookup.get(key)
        if not edge:
            continue

        acc_distance += float(edge.get("distance", 0))
        acc_duration += float(edge.get("duration", 0))
        last_to = to_id

        # Group tiny edge fragments into meaningful route-flow chunks.
        should_emit = (
            acc_distance >= 250
            or acc_duration >= 30
            or i == len(path_ids) - 2
        )
        if not should_emit:
            continue

        start_node = node_lookup.get(chunk_start, {})
        end_node = node_lookup.get(last_to, {})
        chunks.append(
            {
                "step": seg_index,
                "fromId": chunk_start,
                "toId": last_to,
                "fromLabel": f"{start_node.get('lat', 0):.5f}, {start_node.get('lng', 0):.5f}",
                "toLabel": f"{end_node.get('lat', 0):.5f}, {end_node.get('lng', 0):.5f}",
                "distanceM": round(acc_distance, 1),
                "durationS": round(acc_duration, 1),
            }
        )
        seg_index += 1
        chunk_start = last_to
        acc_distance = 0.0
        acc_duration = 0.0

    return chunks


async def reverse_geocode(lat: float, lng: float):
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "pathfinder-local-app/1.0")
    url = "https://nominatim.openstreetmap.org/reverse"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lng,
                "zoom": 10,
                "addressdetails": 1,
            },
            headers={"User-Agent": user_agent},
        )
    if response.status_code >= 400:
        return None
    data = response.json()
    address = data.get("address", {})
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("county")
    )
    state = address.get("state")
    country = address.get("country")
    return {
        "city": city,
        "state": state,
        "country": country,
    }


def parse_coord_node_id(node_id: str):
    if "," not in node_id:
        return None
    parts = node_id.split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


async def build_major_waypoints(route: List[dict]):
    if not route:
        return [], []
    sample_count = min(6, len(route))
    if sample_count <= 1:
        point = route[0]
        return [f"{point['lat']:.4f}, {point['lng']:.4f}"], []

    indices = [round(i * (len(route) - 1) / (sample_count - 1)) for i in range(sample_count)]
    labels = []
    states = []
    for idx in indices:
        point = route[idx]
        geo = await reverse_geocode(point["lat"], point["lng"])
        if geo and geo.get("city"):
            label = geo["city"]
        elif geo and geo.get("state"):
            label = geo["state"]
        else:
            label = f"{point['lat']:.2f}, {point['lng']:.2f}"
        labels.append(label)
        if geo and geo.get("state"):
            states.append(geo["state"])

    # Deduplicate consecutive labels to keep summary clean.
    cleaned_labels = []
    for lbl in labels:
        if not cleaned_labels or cleaned_labels[-1] != lbl:
            cleaned_labels.append(lbl)

    cleaned_states = []
    for st in states:
        if not cleaned_states or cleaned_states[-1] != st:
            cleaned_states.append(st)
    return cleaned_labels, cleaned_states


def build_road_segments(routes: list):
    segments = []
    if not routes:
        return segments

    steps = routes[0].get("legs", [{}])[0].get("steps", [])
    current = None
    for step in steps:
        name = step.get("name") or step.get("ref") or "Unnamed road"
        distance = float(step.get("distance", 0))
        duration = float(step.get("duration", 0))
        if current and current["name"] == name:
            current["distanceM"] += distance
            current["durationS"] += duration
        else:
            if current:
                segments.append(current)
            current = {"name": name, "distanceM": distance, "durationS": duration}
    if current:
        segments.append(current)

    return [
        {
            "name": seg["name"],
            "distanceKm": round(seg["distanceM"] / 1000, 2),
            "durationMin": round(seg["durationS"] / 60, 1),
        }
        for seg in segments[:12]
    ]


def build_state_crossings(states: List[str]):
    if len(states) < 2:
        return []
    crossings = []
    for i in range(len(states) - 1):
        if states[i] != states[i + 1]:
            crossings.append(f"{states[i]} -> {states[i + 1]}")
    return crossings


async def build_trace_labels(trace: List[dict]):
    if not trace:
        return []

    count = len(trace)
    sample_count = min(12, count)
    if sample_count == 1:
        sample_indices = [0]
    else:
        sample_indices = [round(i * (count - 1) / (sample_count - 1)) for i in range(sample_count)]

    labeled_samples = {}
    for idx in sample_indices:
        node_id = trace[idx].get("node", "")
        parsed = parse_coord_node_id(node_id)
        if not parsed:
            labeled_samples[idx] = node_id
            continue

        lat, lng = parsed
        geo = await reverse_geocode(lat, lng)
        if geo and geo.get("city") and geo.get("state"):
            labeled_samples[idx] = f"{geo['city']}, {geo['state']}"
        elif geo and geo.get("state"):
            labeled_samples[idx] = geo["state"]
        else:
            labeled_samples[idx] = node_id

    labels = []
    sorted_indices = sorted(labeled_samples.keys())
    for i in range(count):
        if i in labeled_samples:
            labels.append(labeled_samples[i])
            continue
        nearest_idx = min(sorted_indices, key=lambda s: abs(s - i))
        labels.append(f"Near {labeled_samples[nearest_idx]}")

    return labels


def recommend_algorithm(algorithm: str, node_count: int):
    algo = algorithm.lower()
    if algo in ("bellman", "bellman-ford") and node_count > 3000:
        return {
            "level": "warning",
            "message": "Bellman-Ford is expensive for this graph size. Prefer Dijkstra or A* for faster results."
        }
    if algo == "bfs" and node_count > 3000:
        return {
            "level": "info",
            "message": "BFS ignores weighted costs. Use Dijkstra or A* for weighted shortest paths."
        }
    return {
        "level": "good",
        "message": "Selected algorithm is suitable for this graph."
    }


def compare_algorithm_performance(graph, start_id, end_id, directed, optimize_for):
    timings = {}
    for algo in ("dijkstra", "astar"):
        t0 = time.time()
        try:
            solve_with_cpp(
                nodes=graph["nodes"],
                edges=graph["edges"],
                start_id=start_id,
                end_id=end_id,
                algorithm=algo,
                optimize_for=optimize_for,
                directed=directed,
            )
            timings[algo] = round((time.time() - t0) * 1000, 2)
        except HTTPException:
            continue
    return timings


def solve_with_cpp(nodes, edges, start_id, end_id, algorithm, optimize_for, directed):
    solver_bin = os.getenv("CPP_SOLVER_BIN", os.path.join(os.path.dirname(__file__), "..", "bin", "path_solver"))
    solver_bin = os.path.abspath(solver_bin)

    if not os.path.exists(solver_bin):
        raise HTTPException(
            status_code=500,
            detail=(
                "C++ solver binary not found. Run: `cd backend && ./build_solver.sh`"
            ),
        )

    lines = [
        f"{algorithm} {optimize_for} {1 if directed else 0} {start_id} {end_id}",
        f"{len(nodes)} {len(edges)}",
    ]

    for n in nodes:
        lines.append(f"{n['id']} {n['lat']} {n['lng']}")

    for e in edges:
        lines.append(
            f"{e['from']} {e['to']} {e.get('distance', 1)} {e.get('duration', 1)} {e.get('cost', 1)} {1 if e.get('bidirectional', False) else 0}"
        )

    payload = "\n".join(lines) + "\n"

    result = subprocess.run(
        [solver_bin],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise HTTPException(status_code=500, detail=f"C++ solver process failed. {stderr}".strip())

    output = (result.stdout or "").strip().splitlines()
    if not output:
        raise HTTPException(status_code=500, detail="C++ solver returned no output.")

    header = output[0].strip().split()
    if header[0] != "OK":
        msg = " ".join(header[1:]) if len(header) > 1 else "C++ solver failed"
        raise HTTPException(status_code=400, detail=msg)

    if len(header) < 9:
        raise HTTPException(status_code=500, detail="Invalid C++ solver response format.")

    total_cost = float(header[1])
    visited = int(header[2])
    path_len = int(header[3])
    relaxations = int(header[4])
    pushes = int(header[5])
    queue_peak = int(header[6])
    heuristic_calls = int(header[7])
    trace_count = int(header[8])
    path = output[1 : 1 + path_len]
    trace_lines = output[1 + path_len : 1 + path_len + trace_count]

    if len(path) != path_len:
        raise HTTPException(status_code=500, detail="Incomplete path output from C++ solver.")
    if len(trace_lines) != trace_count:
        raise HTTPException(status_code=500, detail="Incomplete trace output from C++ solver.")

    trace = []
    for line in trace_lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        trace.append(
            {
                "node": parts[0],
                "bestCost": float(parts[1]),
                "frontier": int(parts[2]),
                "visited": int(parts[3]),
                "relaxations": int(parts[4]),
            }
        )

    return path, total_cost, visited, {
        "relaxations": relaxations,
        "queuePushes": pushes,
        "queuePeak": queue_peak,
        "heuristicCalls": heuristic_calls,
        "trace": trace,
    }


class LiveRoutePayload(BaseModel):
    origin: str
    destination: str
    algorithm: str = "dijkstra"
    optimizeFor: str = "distance"
    graphType: str = "directed"


app = FastAPI(title="Pathfinder Python + C++ Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/routes/live")
async def live_route(payload: LiveRoutePayload):
    started = time.time()

    origin = await resolve_place(payload.origin)
    destination = await resolve_place(payload.destination)

    osrm_url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f'{origin["lng"]},{origin["lat"]};{destination["lng"]},{destination["lat"]}'
        "?alternatives=true&overview=full&geometries=geojson&steps=true"
    )

    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.get(osrm_url)

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to fetch route from OSRM.")

    data = response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise HTTPException(status_code=404, detail="No drivable route found for selected locations.")

    directed = payload.graphType == "directed"
    graph = build_graph_from_osrm(data["routes"])
    if not graph["nodes"] or not graph["edges"] or not graph["start_id"] or not graph["end_id"]:
        raise HTTPException(status_code=500, detail="Could not build route graph from OSRM response.")

    path, _, visited, algo_stats = solve_with_cpp(
        nodes=graph["nodes"],
        edges=graph["edges"],
        start_id=graph["start_id"],
        end_id=graph["end_id"],
        algorithm=payload.algorithm,
        optimize_for=payload.optimizeFor,
        directed=directed,
    )

    node_lookup = {node["id"]: node for node in graph["nodes"]}
    edge_lookup = create_edge_lookup(graph["edges"], directed)
    summary = summarize_path(path, node_lookup, edge_lookup)
    detailed_flow = build_detailed_flow(path, node_lookup, edge_lookup)
    major_waypoints, states = await build_major_waypoints(summary["route"])
    state_crossings = build_state_crossings(states)
    road_segments = build_road_segments(data["routes"])
    perf_timings = compare_algorithm_performance(
        graph=graph,
        start_id=graph["start_id"],
        end_id=graph["end_id"],
        directed=directed,
        optimize_for=payload.optimizeFor,
    )
    recommendation = recommend_algorithm(payload.algorithm, len(graph["nodes"]))
    trace_labels = await build_trace_labels(algo_stats["trace"])

    efficiency = (
        round((summary["distance"] / max(visited, 1)), 2) if summary["distance"] > 0 else 0
    )
    distance_km = round(summary["distance"] / 1000, 2)
    distance_miles = round(distance_km * 0.621371, 2)
    duration_hours = summary["duration"] / 3600
    duration_mins = round(summary["duration"] / 60, 1)
    progress_percent = min(100, round((distance_miles / 3000) * 100, 1)) if distance_miles else 0

    perf_insight = None
    current_algo_key = payload.algorithm.lower()
    if current_algo_key in perf_timings and perf_timings:
        best_algo = min(perf_timings, key=perf_timings.get)
        if best_algo != current_algo_key:
            perf_insight = (
                f"{best_algo.upper()} could solve this in ~{perf_timings[best_algo]} ms "
                f"instead of {perf_timings[current_algo_key]} ms."
            )

    return {
        "algorithm": payload.algorithm,
        "optimizeFor": payload.optimizeFor,
        "graphType": payload.graphType,
        "origin": origin,
        "destination": destination,
        "route": summary["route"],
        "metrics": {
            "distanceKm": distance_km,
            "distanceMiles": distance_miles,
            "durationMin": duration_mins,
            "durationHours": round(duration_hours, 2),
            "cost": round(summary["cost"], 2),
            "hops": summary["hops"],
            "exploredNodes": visited,
            "edgeRelaxations": algo_stats["relaxations"],
            "queuePushes": algo_stats["queuePushes"],
            "queuePeak": algo_stats["queuePeak"],
            "heuristicCalls": algo_stats["heuristicCalls"],
            "computeTimeMs": round((time.time() - started) * 1000),
        },
        "pathLabels": path,
        "algorithmTrace": algo_stats["trace"],
        "traceLabels": trace_labels,
        "detailedFlow": detailed_flow,
        "majorWaypoints": major_waypoints,
        "routeBreakdown": {
            "roadSegments": road_segments,
            "stateCrossings": state_crossings,
        },
        "recommendation": recommendation,
        "performanceComparison": {
            "timingsMs": perf_timings,
            "insight": perf_insight,
        },
        "humanMetrics": {
            "distanceText": f"{distance_miles} mi ({distance_km} km)",
            "timeText": f"{int(duration_hours)}h {int(summary['duration'] // 60 % 60)}m",
            "progressPercent": progress_percent,
        },
        "insights": [
            f"{payload.algorithm.upper()} explored {visited} nodes.",
            f"Average effective progress: {efficiency} meters per explored node.",
            f"Objective optimized for: {payload.optimizeFor}.",
        ],
    }
