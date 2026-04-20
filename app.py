import requests
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

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


def estimar_semaforos(distancia_km, duracao_base_min, velocidade_media_kmh):
    if distancia_km <= 0:
        return {"semaforos": 0, "atraso_min": 0, "duracao_ajustada_min": duracao_base_min}
    if velocidade_media_kmh > 60:
        densidade = 0.5
    elif velocidade_media_kmh > 40:
        densidade = 2.0
    else:
        densidade = 3.5
    n_semaforos = round(distancia_km * densidade)
    atraso_s = round(n_semaforos * 0.55 * 28)
    atraso_min = round(atraso_s / 60)
    return {
        "semaforos": n_semaforos,
        "atraso_min": atraso_min,
        "duracao_ajustada_min": duracao_base_min + atraso_min,
    }


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


@app.route("/geocode", methods=["POST"])
def geocode():
    """Geocodifica origem e destino, retorna coords para o frontend chamar HERE."""
    dados = request.get_json()
    end_origem = dados.get("origem", "").strip()
    end_destino = dados.get("destino", "").strip()

    if not end_origem or not end_destino:
        return jsonify({"erro": "Preencha os dois campos."}), 400

    res_origem = geocodificar_endereco(end_origem)
    if not res_origem:
        return jsonify({"erro": f"Local não encontrado: \"{end_origem}\""}), 404

    res_destino = geocodificar_endereco(end_destino)
    if not res_destino:
        return jsonify({"erro": f"Local não encontrado: \"{end_destino}\""}), 404

    return jsonify({
        "origem": {"lat": res_origem[0], "lon": res_origem[1], "nome": res_origem[2]},
        "destino": {"lat": res_destino[0], "lon": res_destino[1], "nome": res_destino[2]},
    })


@app.route("/calcular", methods=["POST"])
def calcular():
    """Recebe rota já calculada do frontend e retorna estatísticas."""
    dados = request.get_json()
    distancia_km = dados.get("distancia_km", 0)
    duracao_min = dados.get("duracao_min", 0)
    transito_status = dados.get("transito_status", "indisponível")

    fator = {"congestionado": 1.6, "moderado": 1.25}.get(transito_status, 1.0)
    duracao_transito = round(duracao_min * fator)
    vel_media = round((distancia_km / max(duracao_min, 1)) * 60, 1)
    semaforos = estimar_semaforos(distancia_km, duracao_transito, vel_media)

    return jsonify({
        "duracao_base_min": duracao_min,
        "duracao_transito_min": duracao_transito,
        "duracao_total_min": semaforos["duracao_ajustada_min"],
        "semaforos": semaforos,
        "velocidade_media": vel_media,
    })


if __name__ == "__main__":
    app.run(debug=True)
