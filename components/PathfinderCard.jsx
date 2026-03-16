"use client";

import { useMemo, useState } from "react";

const CHIPS = ["Distance", "Time", "Cost", "Hops"];

function buildPath(origin, destination, nodes) {
  const middleNodes = Array.from(
    { length: Math.max(0, nodes - 2) },
    (_, index) => `N${index + 1}`
  );
  return [origin, ...middleNodes, destination];
}

export default function PathfinderCard() {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [algorithm, setAlgorithm] = useState("dijkstra");
  const [graphType, setGraphType] = useState("undirected");
  const [activeChip, setActiveChip] = useState("Distance");
  const [isError, setIsError] = useState(false);
  const [result, setResult] = useState(null);

  const pathNodes = useMemo(() => {
    if (!result) return [];
    return buildPath(result.origin, result.destination, result.nodes);
  }, [result]);

  const handleSwap = () => {
    setOrigin(destination);
    setDestination(origin);
  };

  const handleFindPath = () => {
    const cleanOrigin = origin.trim();
    const cleanDestination = destination.trim();

    if (!cleanOrigin || !cleanDestination) {
      setIsError(true);
      setTimeout(() => setIsError(false), 400);
      return;
    }

    const distance = (Math.random() * 40 + 5).toFixed(1);
    const nodes = Math.floor(Math.random() * 6 + 3);
    const calcTime = (Math.random() * 0.8 + 0.1).toFixed(2);

    setResult({
      origin: cleanOrigin,
      destination: cleanDestination,
      distance,
      nodes,
      calcTime
    });
  };

  return (
    <section className="card">
      <header className="header">
        <div className="logo-row">
          <div className="logo-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 12h18M12 3l9 9-9 9" />
            </svg>
          </div>
          <h1>Pathfinder</h1>
        </div>
        <p className="subtitle">Find the shortest route between nodes</p>
      </header>

      <div className="divider" />

      <div className="field-group">
        <div className="route-pair">
          <div className="field">
            <label htmlFor="origin">Origin</label>
            <div className="input-wrap">
              <span className="input-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="10" r="3" />
                  <path d="M12 2a8 8 0 0 1 8 8c0 5-8 13-8 13S4 15 4 10a8 8 0 0 1 8-8z" />
                </svg>
              </span>
              <input
                id="origin"
                type="text"
                value={origin}
                onChange={(event) => setOrigin(event.target.value)}
                placeholder="Enter start node or location"
              />
            </div>
          </div>

          <button className="swap-btn" type="button" onClick={handleSwap} title="Swap">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M7 16V4m0 0L3 8m4-4 4 4M17 8v12m0 0 4-4m-4 4-4-4" />
            </svg>
          </button>

          <div className="field">
            <label htmlFor="destination">Destination</label>
            <div className="input-wrap">
              <span className="input-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 1 1 16 0z" />
                  <circle cx="12" cy="10" r="2" />
                </svg>
              </span>
              <input
                id="destination"
                type="text"
                value={destination}
                onChange={(event) => setDestination(event.target.value)}
                placeholder="Enter end node or location"
              />
            </div>
          </div>
        </div>

        <div className="options-row">
          <div className="field">
            <label htmlFor="algorithm">Algorithm</label>
            <div className="input-wrap">
              <span className="input-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2v-4M9 21H5a2 2 0 0 1-2-2v-4m0 0h18" />
                </svg>
              </span>
              <select
                id="algorithm"
                value={algorithm}
                onChange={(event) => setAlgorithm(event.target.value)}
              >
                <option value="dijkstra">Dijkstra</option>
                <option value="astar">A* Search</option>
                <option value="bfs">BFS</option>
                <option value="bellman">Bellman-Ford</option>
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="graphType">Graph Type</label>
            <div className="input-wrap">
              <span className="input-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="18" cy="5" r="3" />
                  <circle cx="6" cy="12" r="3" />
                  <circle cx="18" cy="19" r="3" />
                  <path d="m8.59 13.51 6.83 3.98M15.41 6.51l-6.82 3.98" />
                </svg>
              </span>
              <select
                id="graphType"
                value={graphType}
                onChange={(event) => setGraphType(event.target.value)}
              >
                <option value="undirected">Undirected</option>
                <option value="directed">Directed</option>
                <option value="weighted">Weighted</option>
              </select>
            </div>
          </div>
        </div>

        <div className="field">
          <label>Optimize For</label>
          <div className="chip-row">
            {CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                className={`chip${activeChip === chip ? " active" : ""}`}
                onClick={() => setActiveChip(chip)}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      </div>

      <button
        type="button"
        className={`btn-find${isError ? " shake" : ""}`}
        onClick={handleFindPath}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        Find Shortest Path
      </button>

      <div className={`result-panel${result ? " show" : ""}`}>
        <div className="result-row">
          <div className="result-metric">
            <div className="val">{result ? `${result.distance} km` : "—"}</div>
            <div className="lbl">Distance</div>
          </div>
          <div className="result-sep" />
          <div className="result-metric">
            <div className="val">{result ? result.nodes : "—"}</div>
            <div className="lbl">Nodes</div>
          </div>
          <div className="result-sep" />
          <div className="result-metric">
            <div className="val">{result ? `${result.calcTime} ms` : "—"}</div>
            <div className="lbl">Calc Time</div>
          </div>
        </div>
        <div className="path-display">
          {pathNodes.map((node, index) => (
            <span key={`${node}-${index}`} className="path-fragment">
              <span className="path-node">{node}</span>
              {index < pathNodes.length - 1 ? <span className="path-arrow">→</span> : null}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
