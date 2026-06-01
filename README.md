# Teseu

Teseu is an urban navigation application built for the city of Sao Paulo. It calculates routes between two addresses using real-time traffic data, supports multiple transportation modes, and features a turn-by-turn navigation interface with live GPS tracking. The application is deployed on Railway and uses HERE Platform for routing and traffic intelligence.

---

## Infrastructure

The application runs on two paid services:

**Railway** — cloud hosting platform responsible for running the Python backend, managing environment variables, and handling all incoming HTTP requests. The server is always on and scales automatically with demand.

**HERE Platform** — provides the routing engine and real-time traffic data. Every route calculation goes through HERE Maps API, which returns optimized paths based on current road conditions, traffic congestion, and transportation mode. Traffic flow data is also consumed in real time to estimate delays and travel times.

---

## Architecture

The project is divided into two layers that work together:

**Backend** (`app.py`) — a Flask server that handles address geocoding via OpenStreetMap Nominatim, receives route statistics from the frontend, estimates traffic delays and traffic lights, and serves the frontend interface. It exposes four endpoints: `/geocode`, `/calcular`, `/decodificar`, and `/sugestoes`.

**Frontend** (`templates/index.html`) — a single-page application with an embedded Leaflet map. It communicates directly with HERE Routing API v8 to compute routes, then sends the result back to the Flask backend for statistical processing. Navigation mode uses the browser Geolocation API with a live bearing calculation to orient the directional arrow.

---

## Features

- Route calculation for car, walking, bicycle, and public transport
- Real-time traffic status with delay estimation
- Traffic light count estimation along the route
- Turn-by-turn navigation with GPS tracking
- Automatic route recalculation when the user deviates from the planned path
- Address autocomplete using OpenStreetMap data
- Route history stored locally in the browser
- Progressive Web App support for installation on mobile devices
- Light and dark theme

---

## Project Structure

```
eleven_maps_v2/
├── app.py                  Flask backend
├── Procfile                Railway startup command
├── requirements.txt        Python dependencies
├── templates/
│   └── index.html          Frontend interface
└── static/
    ├── manifest.json       PWA manifest
    ├── sw.js               Service worker
    ├── icon-192.png        App icon
    └── icon-512.png        App icon
```

---

## Dependencies

**Python**

| Package | Purpose |
|---|---|
| Flask | Web framework and HTTP server |
| Requests | HTTP client for Nominatim and Overpass |
| Gunicorn | Production WSGI server |
| Flexpolyline | Decodes HERE flexible polyline format |

**Frontend**

| Library | Purpose |
|---|---|
| Leaflet 1.9.4 | Interactive map rendering |
| CartoDB Voyager | Map tile layer |
| HERE Routing API v8 | Route calculation and traffic data |
| HERE Traffic API v7 | Real-time traffic flow |
| Nominatim | Reverse geocoding for GPS navigation |

---

## Installation

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/cassioforza-blip/eleven-maps-v2.git
cd eleven-maps-v2
pip install -r requirements.txt
```

---

## Running Locally

```bash
python app.py
```

The server starts at `http://localhost:5000`. An active internet connection is required for geocoding, routing, and map tiles.

---

## Deployment

The application deploys automatically to Railway on every push to the `main` branch. The `Procfile` defines the startup command:

```
web: gunicorn app:app
```

No additional configuration is required on the Railway side beyond setting the repository connection.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/geocode` | Converts two address strings into coordinates |
| POST | `/calcular` | Returns traffic delay and travel time statistics |
| POST | `/decodificar` | Decodes HERE flexible polyline into coordinate array |
| GET | `/sugestoes` | Returns address autocomplete suggestions |

---

## How Routing Works

1. The user enters an origin and destination address.
2. The backend geocodes both addresses using OpenStreetMap Nominatim.
3. The frontend calls HERE Routing API v8 with the coordinates and selected transportation mode.
4. The returned polyline is decoded by the backend and sent back as a coordinate array.
5. The frontend calls HERE Traffic API to obtain real-time speed data along the route.
6. The backend calculates the estimated travel time including traffic delays and traffic light stops.
7. The route is drawn on the map with animated rendering.

---

## Navigation

When navigation mode is activated, the browser Geolocation API begins tracking the user's position. The directional arrow is oriented using the geographic bearing calculated from consecutive GPS positions via the Haversine formula, with smooth angular interpolation to prevent abrupt rotations. If the user deviates more than 80 meters from the planned route, the application automatically recalculates using the current GPS coordinates as the new origin.

---

## Academic Context

This project was developed as part of the Artificial Intelligence course at Universidade Anhanguera — Unidade Mooca, under the guidance of Professor Luiz Antonio.

Student: Cassio Jose da Silva
RA: 12524152007

---

## License

This project is for academic purposes. All routing and traffic data is provided by HERE Technologies under a paid commercial plan. Map tiles are provided by CartoDB and OpenStreetMap contributors under their respective licenses.
