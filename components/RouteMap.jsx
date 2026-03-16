"use client";

import { useEffect } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

const DEFAULT_CENTER = [20, 0];
const DEFAULT_ZOOM = 2;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png"
});

function FitRoute({ route }) {
  const map = useMap();

  useEffect(() => {
    if (!route?.length) return;
    const bounds = L.latLngBounds(route);
    map.fitBounds(bounds, { padding: [32, 32] });
  }, [map, route]);

  return null;
}

export default function RouteMap({ originPoint, destinationPoint, route }) {
  return (
    <div className="map-shell">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom
        className="map-canvas"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {originPoint ? (
          <Marker position={originPoint}>
            <Tooltip permanent direction="top">
              Source
            </Tooltip>
          </Marker>
        ) : null}

        {destinationPoint ? (
          <Marker position={destinationPoint}>
            <Tooltip permanent direction="top">
              Destination
            </Tooltip>
          </Marker>
        ) : null}

        {route?.length ? <Polyline positions={route} color="#4f7ef8" weight={5} /> : null}
        <FitRoute route={route} />
      </MapContainer>
    </div>
  );
}
