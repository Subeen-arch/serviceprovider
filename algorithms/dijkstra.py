"""Dijkstra's shortest path algorithm, implemented by hand.

Nothing here calls a ready-made pathfinding library. The only import used by the
algorithm itself is `heapq`, which is Python's binary heap - a plain data
structure that serves as the priority queue. The distance table, the visited
set, the relaxation step and the path reconstruction are all written out below.

How a route is produced
-----------------------
1. The customer's map location is *snapped* to the nearest junction in the
   graph. That junction is the entry point.
2. Dijkstra runs once from the entry point and produces the shortest distance
   to every junction in the valley (single source, all destinations).
3. A provider's location is snapped to its own nearest junction, and the total
   route is:

       walk to entry junction  +  shortest road path  +  walk to provider

Because step 2 solves every destination at once, ranking twenty providers costs
exactly one run of Dijkstra, not twenty.
"""

import heapq
from math import asin, cos, radians, sin, sqrt

from algorithms.road_graph import EDGES, NODES

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in kilometres between two coordinates."""
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


class RoadGraph:
    """An undirected weighted graph stored as an adjacency list."""

    def __init__(self, nodes=NODES, edges=EDGES):
        self.nodes = nodes
        # adjacency[junction] = [(neighbour, distance in km), ...]
        self.adjacency = {node_id: [] for node_id in nodes}

        for a, b in edges:
            if a not in nodes or b not in nodes:
                raise ValueError(f"Edge ({a}, {b}) refers to an unknown junction")
            _, lat_a, lng_a = nodes[a]
            _, lat_b, lng_b = nodes[b]
            weight = haversine_km(lat_a, lng_a, lat_b, lng_b)
            # Undirected: the road is added in both directions.
            self.adjacency[a].append((b, weight))
            self.adjacency[b].append((a, weight))

    # ------------------------------------------------------------------
    # Dijkstra
    # ------------------------------------------------------------------
    def dijkstra(self, source):
        """Shortest distance from `source` to every reachable junction.

        Returns (distance, previous):
            distance[n] - kilometres from source to n, or infinity if n is
                          not reachable.
            previous[n] - the junction visited just before n on the shortest
                          path, used to rebuild the route.
        """
        if source not in self.adjacency:
            raise ValueError(f"Unknown source junction: {source}")

        distance = {node_id: float("inf") for node_id in self.adjacency}
        previous = {node_id: None for node_id in self.adjacency}
        visited = set()

        distance[source] = 0.0

        # Priority queue of (distance so far, junction). The smallest distance
        # is always removed first, which is the heart of Dijkstra.
        queue = [(0.0, source)]

        while queue:
            current_distance, current = heapq.heappop(queue)

            # A junction can sit in the queue more than once; the first time it
            # comes out it already carries its final shortest distance.
            if current in visited:
                continue
            visited.add(current)

            # Relaxation: can we reach each neighbour faster through `current`?
            for neighbour, weight in self.adjacency[current]:
                if neighbour in visited:
                    continue
                new_distance = current_distance + weight
                if new_distance < distance[neighbour]:
                    distance[neighbour] = new_distance
                    previous[neighbour] = current
                    heapq.heappush(queue, (new_distance, neighbour))

        return distance, previous

    @staticmethod
    def build_path(previous, source, target):
        """Walk the `previous` table backwards to rebuild the route."""
        if source == target:
            return [source]
        if previous.get(target) is None:
            return []  # target was never reached

        path = []
        node = target
        while node is not None:
            path.append(node)
            node = previous[node]
        path.reverse()

        # A valid path must start at the source.
        return path if path[0] == source else []

    # ------------------------------------------------------------------
    # Helpers that connect real coordinates to the graph
    # ------------------------------------------------------------------
    def nearest_node(self, lat, lng):
        """Snap a real coordinate to the closest junction.

        Returns (junction id, distance in km to that junction).
        """
        best_id = None
        best_distance = float("inf")
        for node_id, (_, node_lat, node_lng) in self.nodes.items():
            d = haversine_km(lat, lng, node_lat, node_lng)
            if d < best_distance:
                best_distance = d
                best_id = node_id
        return best_id, best_distance

    def point(self, node_id):
        """The display name and coordinates of a junction."""
        name, lat, lng = self.nodes[node_id]
        return {"name": name, "lat": lat, "lng": lng}


# A single shared graph - it never changes while the app runs.
GRAPH = RoadGraph()


class RouteFinder:
    """Runs Dijkstra once from the customer, then answers many destinations.

    Created per search request:

        finder = RouteFinder(user_lat, user_lng)
        km = finder.distance_to(provider_lat, provider_lng)   # for ranking
        route = finder.route_to(provider_lat, provider_lng)   # for the map
    """

    def __init__(self, lat, lng, graph=GRAPH):
        self.graph = graph
        self.origin = {"lat": lat, "lng": lng}
        # Step 1: snap the customer onto the road network.
        self.entry_node, self.entry_km = graph.nearest_node(lat, lng)
        # Step 2: one Dijkstra run answers every provider.
        self.distance, self.previous = graph.dijkstra(self.entry_node)

    def distance_to(self, lat, lng):
        """Total road distance in km, or None if no route exists."""
        exit_node, exit_km = self.graph.nearest_node(lat, lng)
        road_km = self.distance[exit_node]
        if road_km == float("inf"):
            return None
        return round(self.entry_km + road_km + exit_km, 2)

    def route_to(self, lat, lng):
        """The full route, ready to be drawn on the map.

        Returns a dictionary with `found`, the total distance, the three parts
        it is made of, and the list of points from the customer to the provider.
        """
        exit_node, exit_km = self.graph.nearest_node(lat, lng)
        road_km = self.distance[exit_node]

        if road_km == float("inf"):
            return {
                "found": False,
                "message": "No road route exists between these two locations.",
            }

        junction_ids = self.graph.build_path(self.previous, self.entry_node, exit_node)
        if not junction_ids:
            return {
                "found": False,
                "message": "No road route exists between these two locations.",
            }

        # customer -> junctions -> provider
        points = [{"name": "Your location", **self.origin}]
        points += [self.graph.point(node_id) for node_id in junction_ids]
        points.append({"name": "Provider", "lat": lat, "lng": lng})

        return {
            "found": True,
            "total_km": round(self.entry_km + road_km + exit_km, 2),
            "access_km": round(self.entry_km, 2),
            "road_km": round(road_km, 2),
            "exit_km": round(exit_km, 2),
            "junction_count": len(junction_ids),
            "junctions": [self.graph.nodes[n][0] for n in junction_ids],
            "points": points,
        }
