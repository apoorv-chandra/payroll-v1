import React, { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

/**
 * PinMap — read-only map that drops up to two pins (check-in + check-out)
 * and fits the view around them. Used for the "My Locations" / employer
 * "Locate" screens. No editing, no geofence circle.
 */
export default function PinMap({ pins = [], height = 360 }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || pins.length === 0) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [pins[0].lng, pins[0].lat],
      zoom: 16,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");

    const bounds = new maplibregl.LngLatBounds();
    pins.forEach((p) => {
      const el = document.createElement("div");
      el.style.cssText = `
        width:24px;height:36px;background:${p.color || "#2563EB"};
        clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);
        border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);
      `;
      el.title = p.label || "";
      new maplibregl.Marker({ element: el })
        .setLngLat([p.lng, p.lat])
        .setPopup(p.label ? new maplibregl.Popup({ offset: 24 }).setText(p.label) : undefined)
        .addTo(map);
      bounds.extend([p.lng, p.lat]);
    });
    if (pins.length > 1) {
      map.fitBounds(bounds, { padding: 60, maxZoom: 17 });
    }
    mapRef.current = map;
    return () => map.remove();
  }, [pins]);

  if (pins.length === 0) {
    return (
      <div
        className="rounded-lg border border-dashed border-gray-300 bg-gray-50 flex items-center justify-center text-sm text-gray-500"
        style={{ height }}
      >
        No location captured for this day.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ height }}
      className="rounded-lg overflow-hidden border border-gray-200"
      data-testid="pin-map"
    />
  );
}
