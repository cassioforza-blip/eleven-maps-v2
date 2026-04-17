import gc
import json
import math

import folium
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

HERE_API_KEY = "o1Sag5mVi2b4Y81hY9tXEuGggmUi8W_tX0uaetJFPEg"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "eleven-maps-v2/1.0"

SP_BOUNDS = {"lat_min": -25.3, "lat_max": -19.7, "lon_min": -53.2, "lon_max": -44.1}


def dentro_de_sp(lat, lon):
    return (SP_BOUNDS["lat_min"] <= lat <= SP_BOUNDS["lat_max"] and
            SP_BOUNDS["lon_min"] <= lon <= SP_BOUNDS["lon_max"])


def geocodificar_endereco(texto):
    tentativas = [
        f"{texto.strip()}, São Paulo, Brasil",
        f"{texto.strip()}, SP, Brasil",
        texto.strip(),
    ]
    headers = {"User-Agent": USER_AGENT}
    for consulta in tentativas:
        try:
            r = requests.get(NOMINATIM_URL, params={
                "q": consulta, "format": "jsonv2", "limit": 5,
                "addressdetails": 1, "countrycodes": "br",
                "viewbox": f"{SP_BOUNDS['lon_min']},{SP_BOUNDS['lat_max']},{SP_BOUNDS['lon_max']},{SP_BOUNDS['lat_min']}",
                "bounded": 1,
            }, headers=headers, timeout=10)
            dados = r.json()
            for local in dados:
                lat, lon = float(local["lat"]), float(local["lon"])
                if dentro_de_sp(lat, lon):
                    nome = local.get("display_name", texto)
                    partes = nome.split(",")
                    return lat, lon, ", ".join(p.strip() for p in partes[:4])
        except Exception:
            continue
    return None


def sugerir_locais(texto):
    try:
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(NOMINATIM_URL, params={
            "q": f"{texto.strip()}, São Paulo",
            "format": "jsonv2", "limit": 7, "addressdetails": 1, "countrycodes": "br",
            "viewbox": f"{SP_BOUNDS['lon_min']},{SP_BOUNDS['lat_max']},{SP_BOUNDS['lon_max']},{SP_BOUNDS['lat_min']}",
            "bounded": 1,
        }, headers=headers, timeout=8)
        resultado = []
        for local in r.json():
            lat, lon = float(local["lat"]), float(local["lon"])
            if not dentro_de_sp(lat, lon):
                continue
            nome = local.get("display_name", "")
            partes = nome.split(",")
            nome_curto = ", ".join(p.strip() for p in partes[:4])
            cat = local.get("category", "")
            tipo = local.get("type", "")
            icone = "📍"
            if cat == "amenity":
                if tipo in ("restaurant", "cafe", "bar", "fast_food"): icone = "🍽️"
                elif tipo in ("hospital", "pharmacy"): icone = "🏥"
                elif tipo in ("school", "university"): icone = "🎓"
                elif tipo == "bank": icone = "🏦"
            elif cat == "shop": icone = "🛍️"
            elif cat == "leisure": icone = "🌳"
            elif tipo in ("mall", "supermarket"): icone = "🏬"
            elif cat == "highway": icone = "🛣️"
            resultado.append({"nome": nome_curto, "lat": lat, "lon": lon, "icone": icone})
        return resultado
    except Exception:
        return []


def calcular_rota_here(lat1, lon1, lat2, lon2, modo="fast"):
    """Usa HERE Routing API v8 para calcular a rota."""
    url = "https://router.hereapi.com/v8/routes"
    params = {
        "apiKey": HERE_API_KEY,
        "transportMode": "car",
        "origin": f"{lat1},{lon1}",
        "destination": f"{lat2},{lon2}",
        "return": "polyline,summary,instructions",
        "routingMode": modo,  # "fast" ou "short"
        "spans": "names",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def buscar_transito_here(lat1, lon1, lat2, lon2):
    try:
        url = "https://data.traffic.hereapi.com/v7/flow"
        params = {
            "apiKey": HERE_API_KEY,
            "locationReferencing": "shape",
            "in": f"bbox:{min(lon1,lon2)-0.05},{min(lat1,lat2)-0.05},{max(lon1,lon2)+0.05},{max(lat1,lat2)+0.05}",
        }
        r = requests.get(url, params=params, timeout=8)
        if r.status_code == 200:
            dados = r.json()
            resultados = dados.get("results", [])
            speeds = []
            for res in resultados[:20]:
                speed = res.get("currentFlow", {}).get("speed", 0)
                if speed > 0:
                    speeds.append(speed)
            if speeds:
                avg = sum(speeds) / len(speeds)
                if avg > 60: return {"status": "livre", "cor": "#4ade80", "velocidade_media": round(avg)}
                elif avg > 30: return {"status": "moderado", "cor": "#facc15", "velocidade_media": round(avg)}
                else: return {"status": "congestionado", "cor": "#f87171", "velocidade_media": round(avg)}
    except Exception:
        pass
    return {"status": "indisponível", "cor": "#6b7280", "velocidade_media": 0}


def decodificar_polyline_here(encoded):
    """Decodifica o formato polyline da HERE."""
    import struct
    result = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        b, shift, val = 0, 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            val |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(val >> 1) if (val & 1) else (val >> 1)
        lat += dlat
        b, shift, val = 0, 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            val |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(val >> 1) if (val & 1) else (val >> 1)
        lng += dlng
        result.append((lat * 1e-5, lng * 1e-5))
    return result


def decodificar_flexpolyline(encoded):
    """Decodifica o formato flexpolyline da HERE v8."""
    try:
        import urllib.parse
        # HERE uses a custom format - try simple lat/lng extraction
        coords = []
        # The HERE v8 API returns coordinates in sections
        return coords
    except Exception:
        return []


def extrair_coords_rota(rota_here):
    """Extrai coordenadas da resposta da HERE Routing API v8."""
    coords = []
    try:
        routes = rota_here.get("routes", [])
        if not routes:
            return coords
        route = routes[0]
        for section in route.get("sections", []):
            polyline = section.get("polyline", "")
            if polyline:
                # HERE v8 usa flexible polyline encoding
                decoded = decode_here_polyline(polyline)
                coords.extend(decoded)
    except Exception as e:
        pass
    return coords


def decode_here_polyline(encoded):
    """Decodifica HERE Flexible Polyline."""
    FORMAT_VERSION = 1
    result = []
    try:
        header_char = encoded[0]
        version = ord(header_char) - 63
        if version != FORMAT_VERSION:
            pass

        precision = (ord(encoded[1]) - 63) & 0x0f
        multiplier = 10 ** (-precision)
        third_dim = (ord(encoded[1]) - 63) >> 4
        has_third = third_dim > 0

        index = 2
        last_lat = 0
        last_lng = 0

        def decode_unsigned(enc, idx):
            result = 0
            shift = 0
            while True:
                c = ord(enc[idx]) - 63
                idx += 1
                result |= (c & 0x1f) << shift
                shift += 5
                if c < 0x20:
                    break
            return result, idx

        def to_signed(val):
            if val & 1:
                return ~(val >> 1)
            return val >> 1

        while index < len(encoded):
            val, index = decode_unsigned(encoded, index)
            last_lat += to_signed(val)
            val, index = decode_unsigned(encoded, index)
            last_lng += to_signed(val)
            if has_third:
                val, index = decode_unsigned(encoded, index)
            result.append((last_lat * multiplier, last_lng * multiplier))
    except Exception:
        pass
    return result


def gerar_mapa_html(coords_rota, coord_origem, coord_destino, end_origem, end_destino, duracao_min, distancia_km, transito):
    if not coords_rota:
        return None

    centro = [(coord_origem[0] + coord_destino[0]) / 2, (coord_origem[1] + coord_destino[1]) / 2]
    zoom = 15 if distancia_km < 2 else 14 if distancia_km < 5 else 13 if distancia_km < 15 else 11

    mapa = folium.Map(location=centro, zoom_start=zoom, tiles="CartoDB dark_matter")
    folium.PolyLine(coords_rota, color="#6c63ff", weight=7, opacity=0.9).add_to(mapa)
    folium.PolyLine(coords_rota, color="#a89fff", weight=2, opacity=0.4).add_to(mapa)
    folium.Marker(coord_origem, popup=f"<b>Origem</b><br>{end_origem}",
                  icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(mapa)
    folium.Marker(coord_destino, popup=f"<b>Destino</b><br>{end_destino}",
                  icon=folium.Icon(color="purple", icon="flag", prefix="fa")).add_to(mapa)

    coords_json = json.dumps([[c[0], c[1]] for c in coords_rota])
    transito_json = json.dumps(transito)

    nav_script = f"""
    <script>
    (function() {{
        var routeCoords = {coords_json};
        var transito = {transito_json};
        var currentIndex = 0;
        var animSpeed = 25;
        var marker = null;
        var animInterval = null;
        var isPlaying = false;

        function waitForMap() {{
            var maps = Object.values(window).filter(v => v && v._container && v.setView);
            if (!maps.length) {{ setTimeout(waitForMap, 300); return; }}
            var map = maps[maps.length - 1];

            var carIcon = L.divIcon({{
                className: '',
                html: '<div style="width:26px;height:26px;background:linear-gradient(135deg,#6c63ff,#48bfe3);border-radius:50%;border:3px solid #fff;box-shadow:0 0 16px #6c63ff;"></div>',
                iconSize: [26,26], iconAnchor: [13,13]
            }});
            marker = L.marker(routeCoords[0], {{icon: carIcon}}).addTo(map);

            var corT = transito.cor || '#6b7280';
            var statusT = transito.status || 'indisponível';
            var velT = transito.velocidade_media || 0;

            var panel = document.createElement('div');
            panel.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;background:rgba(14,15,20,0.97);border:1px solid rgba(108,99,255,0.4);border-radius:20px;padding:20px 22px;font-family:Syne,sans-serif;color:#e8eaf0;min-width:240px;box-shadow:0 0 40px rgba(108,99,255,0.2);backdrop-filter:blur(20px);';
            panel.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
                    <div style="font-size:10px;letter-spacing:2.5px;color:#6b7280;text-transform:uppercase;">Navegação</div>
                    <div style="font-size:10px;padding:3px 8px;border-radius:20px;background:${{corT}}22;color:${{corT}};border:1px solid ${{corT}}44;">
                        ${{statusT}}${{velT > 0 ? ' · ' + velT + ' km/h' : ''}}
                    </div>
                </div>
                <div id="npct" style="font-size:38px;font-weight:800;background:linear-gradient(135deg,#6c63ff,#48bfe3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1;">0%</div>
                <div style="margin:12px 0 6px;height:5px;background:#1a1d2e;border-radius:5px;overflow:hidden;">
                    <div id="nbar" style="height:100%;width:0%;background:linear-gradient(90deg,#6c63ff,#48bfe3);border-radius:5px;transition:width 0.15s;"></div>
                </div>
                <div id="nstatus" style="font-size:12px;color:#a89fff;margin-bottom:4px;">Pronto para iniciar</div>
                <div id="nspeed" style="font-size:11px;color:#6b7280;margin-bottom:14px;height:16px;"></div>
                <div style="display:flex;gap:8px;">
                    <button id="nbtn" onclick="window._nav.toggle()" style="flex:1;background:linear-gradient(135deg,#6c63ff,#48bfe3);border:none;border-radius:10px;color:#fff;font-family:Syne,sans-serif;font-weight:700;font-size:13px;padding:10px;cursor:pointer;">▶ Iniciar</button>
                    <button onclick="window._nav.reset()" style="background:#1a1d2e;border:1px solid #2a2d42;border-radius:10px;color:#6b7280;font-size:15px;padding:10px 14px;cursor:pointer;">↺</button>
                </div>
            `;
            document.body.appendChild(panel);

            var watchId = null;
            function startGPS() {{
                if (!navigator.geolocation) return;
                watchId = navigator.geolocation.watchPosition(function(pos) {{
                    var speed = pos.coords.speed;
                    if (speed !== null && speed >= 0) {{
                        document.getElementById('nspeed').textContent = '📍 GPS: ' + Math.round(speed * 3.6) + ' km/h';
                    }}
                }}, null, {{enableHighAccuracy: true, maximumAge: 1000}});
            }}

            window._nav = {{
                toggle: function() {{
                    if (isPlaying) {{
                        clearInterval(animInterval); isPlaying = false;
                        document.getElementById('nbtn').textContent = '▶ Continuar';
                        document.getElementById('nstatus').textContent = 'Pausado';
                    }} else {{
                        if (currentIndex >= routeCoords.length - 1) this.reset();
                        isPlaying = true; startGPS();
                        document.getElementById('nbtn').textContent = '⏸ Pausar';
                        document.getElementById('nstatus').textContent = 'Navegando...';
                        animInterval = setInterval(function() {{
                            if (currentIndex >= routeCoords.length - 1) {{
                                clearInterval(animInterval); isPlaying = false;
                                document.getElementById('nbtn').textContent = '✓ Chegou!';
                                document.getElementById('nstatus').textContent = '🎉 Destino atingido!';
                                document.getElementById('npct').textContent = '100%';
                                document.getElementById('nbar').style.width = '100%';
                                if (watchId) navigator.geolocation.clearWatch(watchId);
                                return;
                            }}
                            currentIndex++;
                            var pos = routeCoords[currentIndex];
                            marker.setLatLng(pos);
                            map.panTo(pos, {{animate:true, duration:0.25}});
                            var pct = Math.round((currentIndex / (routeCoords.length - 1)) * 100);
                            document.getElementById('npct').textContent = pct + '%';
                            document.getElementById('nbar').style.width = pct + '%';
                        }}, animSpeed);
                    }}
                }},
                reset: function() {{
                    clearInterval(animInterval); isPlaying = false; currentIndex = 0;
                    if (watchId) {{ navigator.geolocation.clearWatch(watchId); watchId = null; }}
                    marker.setLatLng(routeCoords[0]);
                    map.panTo(routeCoords[0], {{animate:true}});
                    document.getElementById('nbtn').textContent = '▶ Iniciar';
                    document.getElementById('nstatus').textContent = 'Pronto para iniciar';
                    document.getElementById('npct').textContent = '0%';
                    document.getElementById('nbar').style.width = '0%';
                    document.getElementById('nspeed').textContent = '';
                }}
            }};
        }}
        waitForMap();
    }})();
    </script>
    """
    mapa.get_root().html.add_child(folium.Element(nav_script))
    return mapa._repr_html_()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/sugestoes")
def sugestoes():
    texto = request.args.get("q", "").strip()
    if len(texto) < 3:
        return jsonify([])
    return jsonify(sugerir_locais(texto))


@app.route("/rota", methods=["POST"])
def calcular_rota():
    dados = request.get_json()
    end_origem = dados.get("origem", "").strip()
    end_destino = dados.get("destino", "").strip()
    modo_rota = dados.get("modo_rota", "completo")

    if not end_origem or not end_destino:
        return jsonify({"erro": "Preencha os dois campos."}), 400

    try:
        res_origem = geocodificar_endereco(end_origem)
        if not res_origem:
            return jsonify({"erro": f"Local não encontrado: \"{end_origem}\""}), 404
        coord_origem = (res_origem[0], res_origem[1])
        nome_origem = res_origem[2]

        res_destino = geocodificar_endereco(end_destino)
        if not res_destino:
            return jsonify({"erro": f"Local não encontrado: \"{end_destino}\""}), 404
        coord_destino = (res_destino[0], res_destino[1])
        nome_destino = res_destino[2]

        # Modo de rota HERE
        here_modo = "short" if modo_rota == "principais" else "fast"

        # Calcula rota via HERE
        rota_here = calcular_rota_here(
            coord_origem[0], coord_origem[1],
            coord_destino[0], coord_destino[1],
            here_modo
        )

        # Extrai coordenadas
        coords_rota = extrair_coords_rota(rota_here)
        if not coords_rota:
            return jsonify({"erro": "Não foi possível calcular a rota entre os pontos."}), 404

        # Extrai resumo
        route = rota_here.get("routes", [{}])[0]
        section = route.get("sections", [{}])[0]
        summary = section.get("summary", {})
        distancia_m = summary.get("length", 0)
        duracao_s = summary.get("duration", 0)
        distancia_km = round(distancia_m / 1000, 2)
        duracao_min = round(duracao_s / 60)

        # Trânsito
        transito = buscar_transito_here(
            coord_origem[0], coord_origem[1],
            coord_destino[0], coord_destino[1]
        )

        mapa_html = gerar_mapa_html(
            coords_rota, coord_origem, coord_destino,
            nome_origem, nome_destino, duracao_min, distancia_km, transito
        )

        if not mapa_html:
            return jsonify({"erro": "Erro ao gerar o mapa."}), 500

        return jsonify({
            "mapa_html": mapa_html,
            "distancia_km": distancia_km,
            "duracao_min": duracao_min,
            "pontos_rota": len(coords_rota),
            "nome_origem": nome_origem,
            "nome_destino": nome_destino,
            "transito": transito,
        })

    except requests.exceptions.HTTPError as e:
        return jsonify({"erro": f"Erro na API HERE: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"erro": f"Erro inesperado: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
