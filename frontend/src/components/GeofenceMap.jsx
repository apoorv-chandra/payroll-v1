import React, { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Free OSM raster style — no API key needed.
const STYLE = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

// Build a circle polygon (64 vertices) from center + radius (meters).
function circlePolygon(lng, lat, radiusM, points = 64) {
  const km = radiusM / 1000;
  const coords = [];
  const earthR = 6378.137;
  const distRad = km / earthR;
  const latRad = (lat * Math.PI) / 180;
  const lngRad = (lng * Math.PI) / 180;
  for (let i = 0; i <= points; i++) {
    const brng = (i * 2 * Math.PI) / points;
    const lat2 = Math.asin(Math.sin(latRad) * Math.cos(distRad) + Math.cos(latRad) * Math.sin(distRad) * Math.cos(brng));
    const lng2 =
      lngRad +
      Math.atan2(
        Math.sin(brng) * Math.sin(distRad) * Math.cos(latRad),
        Math.cos(distRad) - Math.sin(latRad) * Math.sin(lat2),
      );
    coords.push([(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
  }
  return { type: "Feature", geometry: { type: "Polygon", coordinates: [coords] }, properties: {} };
}

/**
 * GeofenceMap
 * props:
 *   - value: { center_lat, center_lng, radius_m }
 *   - onChange(next)  // called on commit (drag end / slider release / map click)
 */
export default function GeofenceMap({ value, onChange }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const markerRef = useRef(null);
  const [center, setCenter] = useState({
    lng: value?.center_lng ?? 77.5946,
    lat: value?.center_lat ?? 12.9716, // Bengaluru default
  });
  const [radius, setRadius] = useState(value?.radius_m || 100);

  const commit = useCallback((next) => {
    onChange?.({ center_lat: next.lat, center_lng: next.lng, radius_m: next.r });
  }, [onChange]);

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: [center.lng, center.lat],
      zoom: 15,
      attributionControl: true,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");

    map.on("load", () => {
      map.addSource("fence", { type: "geojson", data: circlePolygon(center.lng, center.lat, radius) });
      map.addLayer({
        id: "fence-fill",
        type: "fill",
        source: "fence",
        paint: { "fill-color": "#2563EB", "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: "fence-line",
        type: "line",
        source: "fence",
        paint: { "line-color": "#2563EB", "line-width": 2 },
      });

      // Draggable center marker
      const el = document.createElement("div");
      el.className = "fence-marker";
      el.style.cssText = "width:18px;height:18px;background:#2563EB;border:3px solid #fff;border-radius:50%;box-shadow:0 0 0 1px #2563EB,0 4px 12px rgba(37,99,235,0.4);cursor:grab;";
      const marker = new maplibregl.Marker({ element: el, draggable: true })
        .setLngLat([center.lng, center.lat])
        .addTo(map);
      markerRef.current = marker;
      marker.on("drag", () => {
        const ll = marker.getLngLat();
        const src = map.getSource("fence");
        if (src) src.setData(circlePolygon(ll.lng, ll.lat, radius));
      });
      marker.on("dragend", () => {
        const ll = marker.getLngLat();
        setCenter({ lng: ll.lng, lat: ll.lat });
        commit({ lng: ll.lng, lat: ll.lat, r: radius });
      });

      // Click-to-set-center
      map.on("click", (e) => {
        const { lng, lat } = e.lngLat;
        marker.setLngLat([lng, lat]);
        const src = map.getSource("fence");
        if (src) src.setData(circlePolygon(lng, lat, radius));
        setCenter({ lng, lat });
        commit({ lng, lat, r: radius });
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update circle when radius changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource) return;
    const src = map.isStyleLoaded() && map.getSource("fence");
    if (src) src.setData(circlePolygon(center.lng, center.lat, radius));
  }, [radius, center.lng, center.lat]);

  // External value changes (e.g. parent saved)
  useEffect(() => {
    if (value?.center_lat == null || value?.center_lng == null) return;
    if (Math.abs(value.center_lat - center.lat) > 1e-6 || Math.abs(value.center_lng - center.lng) > 1e-6) {
      setCenter({ lng: value.center_lng, lat: value.center_lat });
      const map = mapRef.current;
      if (map) {
        map.flyTo({ center: [value.center_lng, value.center_lat], zoom: 15, duration: 700 });
        if (markerRef.current) markerRef.current.setLngLat([value.center_lng, value.center_lat]);
      }
    }
    if (value.radius_m && Math.abs(value.radius_m - radius) > 0.5) setRadius(value.radius_m);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value?.center_lat, value?.center_lng, value?.radius_m]);

  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((p) => {
      const { latitude, longitude } = p.coords;
      setCenter({ lng: longitude, lat: latitude });
      const map = mapRef.current;
      if (map) {
        map.flyTo({ center: [longitude, latitude], zoom: 16, duration: 700 });
        if (markerRef.current) markerRef.current.setLngLat([longitude, latitude]);
      }
      commit({ lng: longitude, lat: latitude, r: radius });
    });
  };

  return (
    <div>
      <div ref={containerRef} className="w-full h-72 sm:h-96 rounded-xl overflow-hidden border border-gray-200" data-testid="fence-map" />
      <div className="mt-3 grid grid-cols-1 sm:grid-cols-[auto_1fr_auto] gap-3 items-center">
        <button
          type="button"
          onClick={useMyLocation}
          data-testid="map-use-location"
          className="h-10 px-3 rounded-md border border-gray-300 bg-white text-sm font-medium hover:bg-gray-50"
        >
          Use my location
        </button>
        <label className="flex items-center gap-3">
          <span className="text-xs uppercase tracking-widest text-gray-500 shrink-0">Radius</span>
          <input
            type="range"
            min={10}
            max={1000}
            step={5}
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            onMouseUp={() => commit({ lng: center.lng, lat: center.lat, r: radius })}
            onTouchEnd={() => commit({ lng: center.lng, lat: center.lat, r: radius })}
            className="w-full accent-[#2563EB]"
            data-testid="fence-radius-slider"
          />
          <span className="text-sm font-medium tabular w-16 text-right">{radius} m</span>
        </label>
        <div className="text-xs text-gray-500 tabular text-right">
          {center.lat.toFixed(5)}, {center.lng.toFixed(5)}
        </div>
      </div>
    </div>
  );
}
