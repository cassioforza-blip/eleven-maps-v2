import json
import requests
import flexpolyline as fp
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
    headers = {"User-Agent": USER_AGENT}
    tentativas = [
        f"{texto.strip()}, São Paulo, Brasil",
        f"{texto.strip()}, SP, Brasil",
        texto.strip(),
    ]
    for consulta in tentativas:
        try:
            r = requests.get(NOMINATIM_URL, params={
                "q": consulta, "format": "jsonv2", "limit": 5,
                "addressdetails": 1, "countrycodes": "br",
                "viewbox": f"{SP_BOUNDS['lon_min']},{SP_BOUNDS['lat_max']},{SP_BOUNDS['lon_max']},{SP_BOUNDS['lat_min']}",
                "bounded": 1,
            }, headers=headers, timeout=10)
            for local in r.json():
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
                if tipo in ("restaurant","cafe","bar","fast_food"): icone = "🍽️"
                elif tipo in ("hospital","pharmacy"): icone = "🏥"
                elif tipo in ("school","university"): icone = "🎓"
                elif tipo == "bank": icone = "🏦"
            elif cat == "shop": icone = "🛍️"
            elif cat == "leisure": icone = "🌳"
            elif tipo in ("mall","supermarket"): icone = "🏬"
            resultado.append({"nome": nome_curto, "lat": lat, "lon": lon, "icone": icone})
        return resultado
    except Exception:
        return []


def calcular_rota_here(lat1, lon1, lat2, lon2, modo="fast", tipo="completo"):
    url = "https://router.hereapi.com/v8/routes"

    # Tipo de via: principais = motorway/trunk/primary, bairros = tudo
    avoid = ""
    if tipo == "principais":
        # Evita vias locais e residenciais
        avoid = "zoneCategory:residential"

    params = {
        "apiKey": HERE_API_KEY,
        "transportMode": "car",
        "origin": f"{lat1},{lon1}",
        "destination": f"{lat2},{lon2}",
        "return": "polyline,summary",
        "routingMode": modo,
        "departureTime": "now",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def estimar_semaforos(distancia_km, duracao_base_s, velocidade_media_kmh):
    """
    Estima número de semáforos e atraso com base em:
    - Densidade média de semáforos em SP: ~3 por km em vias urbanas
    - Ciclo médio de semáforo em SP: 90s (dados CET-SP)
    - Probabilidade de pegar vermelho: ~55%
    - Tempo médio de espera por semáforo: ~25s
    """
    if distancia_km <= 0:
        return {"semaforos": 0, "atraso_s": 0, "duracao_ajustada_min": round(duracao_base_s / 60)}

    # Densidade de semáforos varia por tipo de via
    if velocidade_media_kmh > 60:
        densidade = 0.5  # vias expressas: poucos semáforos
    elif velocidade_media_kmh > 40:
        densidade = 2.0  # vias arteriais
    else:
        densidade = 3.5  # vias locais/bairros

    n_semaforos = round(distancia_km * densidade)
    prob_vermelho = 0.55
    espera_media_s = 28  # dados CET-SP 2023

    atraso_total_s = round(n_semaforos * prob_vermelho * espera_media_s)
    duracao_ajustada_s = duracao_base_s + atraso_total_s
    duracao_ajustada_min = max(1, round(duracao_ajustada_s / 60))

    return {
        "semaforos": n_semaforos,
        "atraso_s": atraso_total_s,
        "duracao_ajustada_min": duracao_ajustada_min,
        "atraso_min": round(atraso_total_s / 60),
    }


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
            speeds = []
            for res in r.json().get("results", [])[:20]:
                speed = res.get("currentFlow", {}).get("speed", 0)
                if speed > 0: speeds.append(speed)
            if speeds:
                avg = sum(speeds) / len(speeds)
                if avg > 60: return {"status": "livre", "cor": "#4ade80", "velocidade_media": round(avg)}
                elif avg > 30: return {"status": "moderado", "cor": "#facc15", "velocidade_media": round(avg)}
                else: return {"status": "congestionado", "cor": "#f87171", "velocidade_media": round(avg)}
    except Exception:
        pass
    return {"status": "indisponível", "cor": "#6b7280", "velocidade_media": 0}


def extrair_coords_rota(rota_here):
    coords = []
    try:
        for route in rota_here.get("routes", []):
            for section in route.get("sections", []):
                polyline = section.get("polyline", "")
                if polyline:
                    decoded = fp.decode(polyline)
                    coords.extend([[lat, lon] for lat, lon, *_ in decoded])
    except Exception as e:
        print(f"Decode error: {e}")
    return coords


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

        tipo_via = dados.get("tipo_via", "completo")  # "principais" ou "bairros"
        here_modo = "short" if modo_rota == "short" else "fast"
        rota_here = calcular_rota_here(
            coord_origem[0], coord_origem[1],
            coord_destino[0], coord_destino[1],
            here_modo, tipo_via
        )

        coords_rota = extrair_coords_rota(rota_here)
        if not coords_rota:
            return jsonify({"erro": "Não foi possível traçar a rota entre os pontos."}), 404

        route = rota_here.get("routes", [{}])[0]
        section = route.get("sections", [{}])[0]
        summary = section.get("summary", {})
        distancia_km = round(summary.get("length", 0) / 1000, 2)
        duracao_min = round(summary.get("duration", 0) / 60)

        transito = buscar_transito_here(
            coord_origem[0], coord_origem[1],
            coord_destino[0], coord_destino[1]
        )

        # Calcula velocidade média
        vel_media = round((distancia_km / max(duracao_min, 1)) * 60, 1) if duracao_min > 0 else 40

        # Ajuste de duração com trânsito real
        fator_transito = 1.0
        if transito["status"] == "congestionado":
            fator_transito = 1.6
        elif transito["status"] == "moderado":
            fator_transito = 1.25
        duracao_com_transito = round(duracao_min * fator_transito)

        # Estimativa de semáforos
        semaforos = estimar_semaforos(distancia_km, duracao_min * 60, vel_media)
        duracao_total = duracao_com_transito + semaforos["atraso_min"]

        return jsonify({
            "coords_rota": coords_rota,
            "distancia_km": distancia_km,
            "duracao_min": duracao_min,
            "duracao_transito_min": duracao_com_transito,
            "duracao_total_min": duracao_total,
            "velocidade_media": vel_media,
            "pontos_rota": len(coords_rota),
            "nome_origem": nome_origem,
            "nome_destino": nome_destino,
            "coord_origem": list(coord_origem),
            "coord_destino": list(coord_destino),
            "transito": transito,
            "semaforos": semaforos,
        })

    except requests.exceptions.HTTPError as e:
        return jsonify({"erro": f"Erro na API HERE: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"erro": f"Erro inesperado: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
