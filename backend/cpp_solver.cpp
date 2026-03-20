#include <algorithm>
#include <cmath>
#include <cctype>
#include <iostream>
#include <limits>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

struct Node {
  std::string id;
  double lat;
  double lng;
};

struct Edge {
  std::string from;
  std::string to;
  double distance;
  double duration;
  double cost;
  int bidirectional;
};

struct AdjEdge {
  std::string to;
  double weight;
};

struct TraceStep {
  std::string node;
  double bestCost;
  long long frontier;
  long long visited;
  long long relaxations;
};

struct SolveResult {
  std::vector<std::string> path;
  double cost = std::numeric_limits<double>::infinity();
  long long visited = 0;
  long long relaxations = 0;
  long long pushes = 0;
  long long queuePeak = 0;
  long long heuristicCalls = 0;
  std::vector<TraceStep> trace;
  bool hasError = false;
  std::string errorMessage;
};

static constexpr double INF = std::numeric_limits<double>::infinity();
static constexpr size_t MAX_TRACE = 1500;

std::vector<std::string> reconstructPath(const std::unordered_map<std::string, std::string>& cameFrom,
                                         const std::string& start,
                                         const std::string& end) {
  if (start == end) return {start};
  auto it = cameFrom.find(end);
  if (it == cameFrom.end()) return {};

  std::vector<std::string> path;
  std::string cur = end;
  path.push_back(cur);

  while (cur != start) {
    auto jt = cameFrom.find(cur);
    if (jt == cameFrom.end()) return {};
    cur = jt->second;
    path.push_back(cur);
  }

  std::reverse(path.begin(), path.end());
  return path;
}

double haversineMeters(double lat1, double lon1, double lat2, double lon2) {
  const double R = 6371000.0;
  auto toRad = [](double x) { return x * M_PI / 180.0; };
  lat1 = toRad(lat1);
  lon1 = toRad(lon1);
  lat2 = toRad(lat2);
  lon2 = toRad(lon2);
  const double dLat = lat2 - lat1;
  const double dLon = lon2 - lon1;

  const double a = std::pow(std::sin(dLat / 2.0), 2) +
                   std::cos(lat1) * std::cos(lat2) * std::pow(std::sin(dLon / 2.0), 2);
  return 2.0 * R * std::asin(std::sqrt(a));
}

void pushTrace(SolveResult& r, const std::string& node, double bestCost, long long frontier) {
  if (r.trace.size() >= MAX_TRACE) return;
  r.trace.push_back({node, bestCost, frontier, r.visited, r.relaxations});
}

SolveResult dijkstra(const std::unordered_map<std::string, std::vector<AdjEdge>>& adj,
                     const std::string& start,
                     const std::string& end) {
  using QItem = std::pair<double, std::string>;
  std::priority_queue<QItem, std::vector<QItem>, std::greater<QItem>> pq;
  std::unordered_map<std::string, double> dist;
  std::unordered_map<std::string, std::string> cameFrom;

  SolveResult r;
  dist[start] = 0.0;
  pq.push({0.0, start});
  r.pushes = 1;
  r.queuePeak = 1;

  while (!pq.empty()) {
    auto [currCost, curr] = pq.top();
    pq.pop();

    if (currCost > (dist.count(curr) ? dist[curr] : INF)) continue;
    r.visited++;
    pushTrace(r, curr, currCost, static_cast<long long>(pq.size()));
    if (curr == end) break;

    auto it = adj.find(curr);
    if (it == adj.end()) continue;
    for (const auto& e : it->second) {
      r.relaxations++;
      double nextCost = currCost + e.weight;
      if (!dist.count(e.to) || nextCost < dist[e.to]) {
        dist[e.to] = nextCost;
        cameFrom[e.to] = curr;
        pq.push({nextCost, e.to});
        r.pushes++;
        r.queuePeak = std::max(r.queuePeak, static_cast<long long>(pq.size()));
      }
    }
  }

  r.path = reconstructPath(cameFrom, start, end);
  r.cost = dist.count(end) ? dist[end] : INF;
  return r;
}

SolveResult bfs(const std::unordered_map<std::string, std::vector<AdjEdge>>& adj,
                const std::string& start,
                const std::string& end) {
  std::queue<std::string> q;
  std::unordered_set<std::string> seen;
  std::unordered_map<std::string, std::string> cameFrom;

  SolveResult r;
  q.push(start);
  seen.insert(start);
  r.pushes = 1;
  r.queuePeak = 1;

  while (!q.empty()) {
    std::string curr = q.front();
    q.pop();
    r.visited++;
    double levelCost = static_cast<double>(r.visited - 1);
    pushTrace(r, curr, levelCost, static_cast<long long>(q.size()));
    if (curr == end) break;

    auto it = adj.find(curr);
    if (it == adj.end()) continue;
    for (const auto& e : it->second) {
      r.relaxations++;
      if (seen.count(e.to)) continue;
      seen.insert(e.to);
      cameFrom[e.to] = curr;
      q.push(e.to);
      r.pushes++;
      r.queuePeak = std::max(r.queuePeak, static_cast<long long>(q.size()));
    }
  }

  r.path = reconstructPath(cameFrom, start, end);
  r.cost = r.path.empty() ? INF : static_cast<double>(r.path.size() - 1);
  return r;
}

SolveResult astar(const std::unordered_map<std::string, std::vector<AdjEdge>>& adj,
                  const std::unordered_map<std::string, Node>& nodeMap,
                  const std::string& start,
                  const std::string& end,
                  double heuristicScale) {
  using QItem = std::pair<double, std::string>;
  std::priority_queue<QItem, std::vector<QItem>, std::greater<QItem>> open;
  std::unordered_map<std::string, double> g;
  std::unordered_map<std::string, double> f;
  std::unordered_map<std::string, std::string> cameFrom;

  SolveResult r;

  auto heuristic = [&](const std::string& id) {
    r.heuristicCalls++;
    auto itA = nodeMap.find(id);
    auto itB = nodeMap.find(end);
    if (itA == nodeMap.end() || itB == nodeMap.end()) return 0.0;
    return haversineMeters(itA->second.lat, itA->second.lng, itB->second.lat, itB->second.lng) *
           heuristicScale;
  };

  g[start] = 0.0;
  f[start] = heuristic(start);
  open.push({f[start], start});
  r.pushes = 1;
  r.queuePeak = 1;

  while (!open.empty()) {
    auto [currF, curr] = open.top();
    open.pop();

    if (currF > (f.count(curr) ? f[curr] : INF)) continue;
    r.visited++;
    pushTrace(r, curr, g.count(curr) ? g[curr] : INF, static_cast<long long>(open.size()));
    if (curr == end) break;

    auto it = adj.find(curr);
    if (it == adj.end()) continue;

    for (const auto& e : it->second) {
      r.relaxations++;
      double tentative = (g.count(curr) ? g[curr] : INF) + e.weight;
      if (!g.count(e.to) || tentative < g[e.to]) {
        cameFrom[e.to] = curr;
        g[e.to] = tentative;
        double nf = tentative + heuristic(e.to);
        f[e.to] = nf;
        open.push({nf, e.to});
        r.pushes++;
        r.queuePeak = std::max(r.queuePeak, static_cast<long long>(open.size()));
      }
    }
  }

  r.path = reconstructPath(cameFrom, start, end);
  r.cost = g.count(end) ? g[end] : INF;
  return r;
}

SolveResult bellmanFord(const std::vector<Node>& nodes,
                        const std::vector<Edge>& edges,
                        const std::string& start,
                        const std::string& end,
                        const std::string& optimizeFor,
                        bool directed) {
  std::unordered_map<std::string, double> dist;
  std::unordered_map<std::string, std::string> cameFrom;
  for (const auto& n : nodes) dist[n.id] = INF;
  dist[start] = 0.0;

  std::vector<Edge> allEdges = edges;
  if (!directed) {
    for (const auto& e : edges) {
      allEdges.push_back({e.to, e.from, e.distance, e.duration, e.cost, e.bidirectional});
    }
  }

  auto weightOf = [&](const Edge& e) {
    if (optimizeFor == "time") return e.duration;
    if (optimizeFor == "cost") return e.cost;
    if (optimizeFor == "hops") return 1.0;
    return e.distance;
  };

  SolveResult r;
  for (size_t i = 0; i + 1 < nodes.size(); i++) {
    bool changed = false;
    for (const auto& e : allEdges) {
      r.relaxations++;
      double w = weightOf(e);
      if (dist[e.from] + w < dist[e.to]) {
        dist[e.to] = dist[e.from] + w;
        cameFrom[e.to] = e.from;
        changed = true;
      }
    }
    r.visited++;
    pushTrace(r, "iteration-" + std::to_string(i + 1), 0, 0);
    if (!changed) break;
  }

  for (const auto& e : allEdges) {
    double w = weightOf(e);
    if (dist[e.from] + w < dist[e.to]) {
      r.hasError = true;
      r.errorMessage = "Negative cycle detected";
      return r;
    }
  }

  r.path = reconstructPath(cameFrom, start, end);
  r.cost = dist[end];
  return r;
}

int main() {
  std::ios::sync_with_stdio(false);
  std::cin.tie(nullptr);

  std::string algorithm, optimizeFor, start, end;
  int directedFlag;
  if (!(std::cin >> algorithm >> optimizeFor >> directedFlag >> start >> end)) {
    std::cout << "ERR Invalid input header\n";
    return 0;
  }

  int n, m;
  if (!(std::cin >> n >> m)) {
    std::cout << "ERR Invalid graph size\n";
    return 0;
  }

  std::vector<Node> nodes;
  nodes.reserve(n);
  std::unordered_map<std::string, Node> nodeMap;
  for (int i = 0; i < n; i++) {
    Node node;
    if (!(std::cin >> node.id >> node.lat >> node.lng)) {
      std::cout << "ERR Invalid node\n";
      return 0;
    }
    nodes.push_back(node);
    nodeMap[node.id] = node;
  }

  std::vector<Edge> edges;
  edges.reserve(m);
  std::unordered_map<std::string, std::vector<AdjEdge>> adj;

  auto weightOfAdj = [&](const Edge& e) {
    if (optimizeFor == "time") return e.duration;
    if (optimizeFor == "cost") return e.cost;
    if (optimizeFor == "hops") return 1.0;
    return e.distance;
  };

  for (int i = 0; i < m; i++) {
    Edge edge;
    if (!(std::cin >> edge.from >> edge.to >> edge.distance >> edge.duration >> edge.cost >> edge.bidirectional)) {
      std::cout << "ERR Invalid edge\n";
      return 0;
    }
    edges.push_back(edge);
    double w = weightOfAdj(edge);
    adj[edge.from].push_back({edge.to, w});
    if (!directedFlag || edge.bidirectional) {
      adj[edge.to].push_back({edge.from, w});
    }
  }

  // In directed graphs, destination often has no outgoing edges and may be absent in `adj`.
  // Validate start/end against node catalog, not adjacency buckets.
  if (!nodeMap.count(start) || !nodeMap.count(end)) {
    std::cout << "ERR Start or destination missing from graph nodes\n";
    return 0;
  }

  std::string lower = algorithm;
  for (auto& c : lower) c = static_cast<char>(std::tolower(c));

  SolveResult r;
  if (lower == "bfs") {
    r = bfs(adj, start, end);
  } else if (lower == "astar" || lower == "a*") {
    double scale = 1.0;
    if (optimizeFor == "time") scale = 1.0 / 13.0;
    else if (optimizeFor == "cost") scale = 0.002;
    else if (optimizeFor == "hops") scale = 0.0;
    r = astar(adj, nodeMap, start, end, scale);
  } else if (lower == "bellman" || lower == "bellman-ford") {
    r = bellmanFord(nodes, edges, start, end, optimizeFor, directedFlag == 1);
  } else {
    r = dijkstra(adj, start, end);
  }

  if (r.hasError) {
    std::cout << "ERR " << r.errorMessage << "\n";
    return 0;
  }

  if (r.path.empty()) {
    std::cout << "ERR No path found\n";
    return 0;
  }

  std::cout << "OK " << r.cost << " " << r.visited << " " << r.path.size() << " " << r.relaxations << " "
            << r.pushes << " " << r.queuePeak << " " << r.heuristicCalls << " " << r.trace.size() << "\n";
  for (const auto& id : r.path) {
    std::cout << id << "\n";
  }
  for (const auto& t : r.trace) {
    std::cout << t.node << " " << t.bestCost << " " << t.frontier << " " << t.visited << " "
              << t.relaxations << "\n";
  }

  return 0;
}
