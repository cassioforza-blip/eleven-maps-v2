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


def calcular_rota_here(lat1, lon1, lat2, lon2, modo="fast"):
    url = "https://router.hereapi.com/v8/routes"
    params = {
        "apiKey": HERE_API_KEY,
        "transportMode": "car",
        "origin": f"{lat1},{lon1}",
        "destination": f"{lat2},{lon2}",
        "return": "polyline,summary",
        "routingMode": modo,
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

        here_modo = "short" if modo_rota == "principais" else "fast"
        rota_here = calcular_rota_here(
            coord_origem[0], coord_origem[1],
            coord_destino[0], coord_destino[1],
            here_modo
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

        return jsonify({
            "coords_rota": coords_rota,
            "distancia_km": distancia_km,
            "duracao_min": duracao_min,
            "pontos_rota": len(coords_rota),
            "nome_origem": nome_origem,
            "nome_destino": nome_destino,
            "coord_origem": list(coord_origem),
            "coord_destino": list(coord_destino),
            "transito": transito,
        })

    except requests.exceptions.HTTPError as e:
        return jsonify({"erro": f"Erro na API HERE: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"erro": f"Erro inesperado: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
