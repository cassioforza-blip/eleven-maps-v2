import gc
import heapq
import json
import math
import time
import hashlib

import folium
import networkx as nx
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# Cache simples em memória para dados OSM
_osm_cache = {}
_cache_max = 20

HERE_API_KEY = "o1Sag5mVi2b4Y81hY9tXEuGggmUi8W_tX0uaetJFPEg"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
USER_AGENT = "eleven-maps-v2/1.0"

TIPOS_PRINCIPAIS = {
    "motorway", "trunk", "primary", "secondary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
}
TIPOS_BAIRROS = {
    "tertiary", "unclassified", "residential", "living_street",
    "service", "tertiary_link",
}
TODOS_TIPOS = TIPOS_PRINCIPAIS | TIPOS_BAIRROS

SP_BOUNDS = {"lat_min": -25.3, "lat_max": -19.7, "lon_min": -53.2, "lon_max": -44.1}


class FalhaMapa(Exception):
    pass


def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def requisicao_json(url, *, params=None, data=None, timeout=30):
    headers = {"User-Agent": USER_AGENT}
    if data is None:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
    else:
        r = requests.post(url, data=data, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def dentro_de_sp(lat, lon):
    return (SP_BOUNDS["lat_min"] <= lat <= SP_BOUNDS["lat_max"] and
            SP_BOUNDS["lon_min"] <= lon <= SP_BOUNDS["lon_max"])


def geocodificar_endereco(texto):
    tentativas = [
        f"{texto.strip()}, São Paulo, Brasil",
        f"{texto.strip()}, SP, Brasil",
        f"{texto.strip()}, Brasil",
        texto.strip(),
    ]
    for consulta in tentativas:
        try:
            dados = requisicao_json(NOMINATIM_URL, params={
                "q": consulta, "format": "jsonv2", "limit": 5,
                "addressdetails": 1, "countrycodes": "br",
                "viewbox": f"{SP_BOUNDS['lon_min']},{SP_BOUNDS['lat_max']},{SP_BOUNDS['lon_max']},{SP_BOUNDS['lat_min']}",
                "bounded": 1,
            })
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
        dados = requisicao_json(NOMINATIM_URL, params={
            "q": f"{texto.strip()}, São Paulo",
            "format": "jsonv2", "limit": 7, "addressdetails": 1, "countrycodes": "br",
            "viewbox": f"{SP_BOUNDS['lon_min']},{SP_BOUNDS['lat_max']},{SP_BOUNDS['lon_max']},{SP_BOUNDS['lat_min']}",
            "bounded": 1,
        })
        resultado = []
        for local in dados:
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


def buscar_transito_here(lat1, lon1, lat2, lon2):
    """Busca dados de trânsito via HERE Traffic API."""
    try:
        url = "https://data.traffic.hereapi.com/v7/flow"
        params = {
            "locationReferencing": "shape",
            "in": f"bbox:{min(lon1,lon2)-0.05},{min(lat1,lat2)-0.05},{max(lon1,lon2)+0.05},{max(lat1,lat2)+0.05}",
            "apiKey": HERE_API_KEY,
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            dados = r.json()
            resultados = dados.get("results", [])
            if resultados:
                speeds = []
                for res in resultados[:20]:
                    current = res.get("currentFlow", {})
                    speed = current.get("speed", 0)
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


def baixar_dados_viarios(origem, destino, modo="completo"):
    tipos = TIPOS_PRINCIPAIS if modo == "principais" else TODOS_TIPOS
    dist = haversine(origem[0], origem[1], destino[0], destino[1])
    raio_seg = 3000
    if dist <= raio_seg * 1.4:
        lat_c = (origem[0] + destino[0]) / 2
        lon_c = (origem[1] + destino[1]) / 2
        raio = max(2000, int(dist * 0.65))
        raio = min(raio, raio_seg)
        segmentos = [(lat_c, lon_c, raio)]
    else:
        n = min(int(dist / raio_seg) + 2, 4)
        segmentos = []
        for i in range(n):
            t = i / (n - 1)
            lat = origem[0] + t * (destino[0] - origem[0])
            lon = origem[1] + t * (destino[1] - origem[1])
            segmentos.append((lat, lon, raio_seg))

    elementos = {}
    for lat_c, lon_c, raio in segmentos:
        filtro_highway = "|".join(tipos)
        consulta = f"""
        [out:json][timeout:45];
        (way["highway"~"^({filtro_highway})$"](around:{raio},{lat_c},{lon_c}););
        (._;>;);
        out body;
        """
        # Chave de cache para este segmento
        cache_key = hashlib.md5(consulta.encode()).hexdigest()
        if cache_key in _osm_cache:
            for el in _osm_cache[cache_key]:
                elementos[el["id"]] = el
            continue

        for url in OVERPASS_URLS:
            baixou = False
            try:
                dados = requisicao_json(url, data={"data": consulta}, timeout=55)
                els = dados.get("elements", [])
                for el in els:
                    elementos[el["id"]] = el
                # Salva no cache
                if len(_osm_cache) >= _cache_max:
                    _osm_cache.pop(next(iter(_osm_cache)))
                _osm_cache[cache_key] = els
                baixou = True
            except requests.RequestException as e:
                if "429" in str(e):
                    time.sleep(5)
                continue
            if baixou:
                break

    if not elementos:
        raise FalhaMapa("Não foi possível baixar dados viários.")
    return {"elements": list(elementos.values())}


def construir_grafo(dados, modo="completo"):
    tipos = TIPOS_PRINCIPAIS if modo == "principais" else TODOS_TIPOS
    G = nx.DiGraph()
    coords = {}
    for el in dados.get("elements", []):
        if el.get("type") == "node":
            coords[el["id"]] = (el["lat"], el["lon"])
            G.add_node(el["id"], y=el["lat"], x=el["lon"])
    for el in dados.get("elements", []):
        if el.get("type") != "way": continue
        tags = el.get("tags", {})
        if tags.get("highway") not in tipos: continue
        nos = el.get("nodes", [])
        if len(nos) < 2: continue
        oneway = str(tags.get("oneway", "no")).lower()
        nome = tags.get("name", "Rua sem nome")
        for o, d in zip(nos, nos[1:]):
            if o not in coords or d not in coords: continue
            dist = haversine(*coords[o], *coords[d])
            if oneway in {"yes", "true", "1"}:
                G.add_edge(o, d, length=dist, name=nome)
            elif oneway == "-1":
                G.add_edge(d, o, length=dist, name=nome)
            else:
                G.add_edge(o, d, length=dist, name=nome)
                G.add_edge(d, o, length=dist, name=nome)
    return G


def no_mais_proximo(G, coord):
    lat, lon = coord
    melhor, menor = None, float("inf")
    for no, dados in G.nodes(data=True):
        dist = haversine(lat, lon, dados["y"], dados["x"])
        if dist < menor:
            menor = dist
            melhor = no
    if melhor is None:
        raise FalhaMapa("Nenhum nó próximo encontrado.")
    return melhor


def heuristica(G, atual, destino):
    a, d = G.nodes[atual], G.nodes[destino]
    return haversine(a["y"], a["x"], d["y"], d["x"])


def a_estrela(G, origem, destino):
    fila = [(0.0, 0, origem)]
    contador = 0
    custo = {origem: 0.0}
    veio_de = {}
    explorados = set()
    nos_expandidos = 0
    while fila:
        _, _, atual = heapq.heappop(fila)
        if atual in explorados: continue
        explorados.add(atual)
        nos_expandidos += 1
        if atual == destino:
            caminho = [destino]
            while caminho[-1] != origem:
                caminho.append(veio_de[caminho[-1]])
            caminho.reverse()
            return caminho, custo[destino], nos_expandidos
        for viz in G.neighbors(atual):
            novo = custo[atual] + G[atual][viz]["length"]
            if viz not in custo or novo < custo[viz]:
                custo[viz] = novo
                veio_de[viz] = atual
                prioridade = novo + heuristica(G, viz, destino)
                contador += 1
                heapq.heappush(fila, (prioridade, contador, viz))
    return None, float("inf"), nos_expandidos


def gerar_mapa_html(G, caminho, coord_origem, coord_destino, end_origem, end_destino, custo, transito):
    coords_rota = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in caminho]
    centro = [(coord_origem[0] + coord_destino[0]) / 2, (coord_origem[1] + coord_destino[1]) / 2]
    dist_km = custo / 1000
    zoom = 15 if dist_km < 2 else 14 if dist_km < 5 else 13 if dist_km < 15 else 11

    mapa = folium.Map(location=centro, zoom_start=zoom, tiles="CartoDB dark_matter")
    folium.PolyLine(coords_rota, color="#6c63ff", weight=7, opacity=0.9).add_to(mapa)
    folium.PolyLine(coords_rota, color="#a89fff", weight=2, opacity=0.4).add_to(mapa)
    folium.Marker(coord_origem, popup=f"<b>Origem</b><br>{end_origem}",
                  icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(mapa)
    folium.Marker(coord_destino, popup=f"<b>Destino</b><br>{end_destino}",
                  icon=folium.Icon(color="purple", icon="flag", prefix="fa")).add_to(mapa)

    coords_json = json.dumps(coords_rota)
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
                html: '<div style="width:26px;height:26px;background:linear-gradient(135deg,#6c63ff,#48bfe3);border-radius:50%;border:3px solid #fff;box-shadow:0 0 16px #6c63ff,0 0 4px #48bfe3;transition:all 0.2s;"></div>',
                iconSize: [26,26], iconAnchor: [13,13]
            }});
            marker = L.marker(routeCoords[0], {{icon: carIcon}}).addTo(map);

            var corTransito = transito.cor || '#6b7280';
            var statusTransito = transito.status || 'indisponível';
            var velTransito = transito.velocidade_media || 0;

            var panel = document.createElement('div');
            panel.id = 'nav-panel';
            panel.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;background:rgba(14,15,20,0.97);border:1px solid rgba(108,99,255,0.4);border-radius:20px;padding:20px 22px;font-family:Syne,sans-serif;color:#e8eaf0;min-width:240px;box-shadow:0 0 40px rgba(108,99,255,0.2),0 8px 32px rgba(0,0,0,0.6);backdrop-filter:blur(20px);';
            panel.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
                    <div style="font-size:10px;letter-spacing:2.5px;color:#6b7280;text-transform:uppercase;">Navegação</div>
                    <div style="font-size:10px;padding:3px 8px;border-radius:20px;background:${{corTransito}}22;color:${{corTransito}};border:1px solid ${{corTransito}}44;">
                        ${{statusTransito}}${{velTransito > 0 ? ' · ' + velTransito + ' km/h' : ''}}
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

            // GPS Speed tracking
            var watchId = null;
            function startGPS() {{
                if (!navigator.geolocation) return;
                watchId = navigator.geolocation.watchPosition(function(pos) {{
                    var speed = pos.coords.speed;
                    if (speed !== null && speed >= 0) {{
                        var kmh = Math.round(speed * 3.6);
                        document.getElementById('nspeed').textContent = '📍 GPS: ' + kmh + ' km/h';
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
                        isPlaying = true;
                        startGPS();
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
    modo_rota = dados.get("modo_rota", "completo")  # "principais" ou "completo"

    if not end_origem or not end_destino:
        return jsonify({"erro": "Preencha os dois campos."}), 400

    G = None
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

        # Busca trânsito em paralelo
        transito = buscar_transito_here(coord_origem[0], coord_origem[1], coord_destino[0], coord_destino[1])

        dados_osm = baixar_dados_viarios(coord_origem, coord_destino, modo_rota)
        G = construir_grafo(dados_osm, modo_rota)
        del dados_osm
        gc.collect()

        if G.number_of_nodes() == 0:
            return jsonify({"erro": "Nenhum dado viário encontrado."}), 500

        no_orig = no_mais_proximo(G, coord_origem)
        no_dest = no_mais_proximo(G, coord_destino)
        caminho, custo_total, nos_exp = a_estrela(G, no_orig, no_dest)

        if caminho is None:
            if modo_rota == "principais":
                return jsonify({"erro": "Sem rota por vias principais. Tente o modo completo."}), 404
            return jsonify({"erro": "Nenhum caminho encontrado entre os pontos."}), 404

        nos_grafo = G.number_of_nodes()
        mapa_html = gerar_mapa_html(G, caminho, coord_origem, coord_destino,
                                    nome_origem, nome_destino, custo_total, transito)
        del G
        gc.collect()

        return jsonify({
            "mapa_html": mapa_html,
            "distancia_km": round(custo_total / 1000, 2),
            "cruzamentos": len(caminho),
            "nos_expandidos": nos_exp,
            "nos_grafo": nos_grafo,
            "nome_origem": nome_origem,
            "nome_destino": nome_destino,
            "transito": transito,
        })

    except FalhaMapa as e:
        return jsonify({"erro": str(e)}), 500
    except Exception as e:
        return jsonify({"erro": f"Erro inesperado: {str(e)}"}), 500
    finally:
        if G is not None:
            del G
        gc.collect()


if __name__ == "__main__":
    app.run(debug=True)
