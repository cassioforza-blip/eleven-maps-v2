# Teseu

Teseu é uma aplicação de navegação urbana desenvolvida para a cidade de São Paulo. Calcula rotas entre dois endereços com dados de trânsito em tempo real, suporta múltiplos modos de transporte e possui interface de navegação guiada com rastreamento GPS ao vivo. A aplicação está hospedada no Railway e utiliza a HERE Platform para roteamento e inteligência de tráfego.

---

## Infraestrutura

A aplicação utiliza dois serviços pagos:

**Railway** — plataforma de hospedagem em nuvem responsável por executar o servidor Python, gerenciar variáveis de ambiente e processar todas as requisições HTTP. O servidor permanece ativo continuamente e escala automaticamente conforme a demanda.

**HERE Platform** — fornece o motor de roteamento e os dados de trânsito em tempo real. Cada cálculo de rota passa pela HERE Maps API v8, que retorna trajetos otimizados com base nas condições atuais das vias, congestionamento e modo de transporte selecionado. Os dados de fluxo de tráfego também são consumidos em tempo real para estimar atrasos e tempos de viagem.

---

## Arquitetura

O projeto é dividido em duas camadas que trabalham em conjunto:

**Backend** (`app.py`) — servidor Flask responsável pela geocodificação de endereços via OpenStreetMap Nominatim, processamento das estatísticas de rota, estimativa de atrasos por trânsito e semáforos, e entrega da interface ao navegador. Expõe quatro endpoints: `/geocode`, `/calcular`, `/decodificar` e `/sugestoes`.

**Frontend** (`templates/index.html`) — aplicação de página única com mapa Leaflet integrado. Comunica-se diretamente com a HERE Routing API v8 para calcular rotas e envia o resultado ao backend Flask para processamento estatístico. O modo de navegação utiliza a API de Geolocalização do navegador com cálculo de bearing geográfico em tempo real para orientar a seta direcional.

---

## Funcionalidades

- Cálculo de rotas para carro, a pé, bicicleta e transporte público
- Status de trânsito em tempo real com estimativa de atraso
- Estimativa da quantidade de semáforos ao longo da rota
- Navegação guiada com rastreamento GPS
- Recalculo automático de rota quando o usuário desvia do trajeto planejado
- Autocomplete de endereços com dados do OpenStreetMap
- Histórico de rotas armazenado localmente no navegador
- Suporte a Progressive Web App para instalação em dispositivos móveis
- Tema claro e escuro

---

## Estrutura do Projeto

```
eleven_maps_v2/
├── app.py                  Servidor backend Flask
├── Procfile                Comando de inicialização no Railway
├── requirements.txt        Dependências Python
├── templates/
│   └── index.html          Interface frontend
└── static/
    ├── manifest.json       Manifesto PWA
    ├── sw.js               Service worker
    ├── icon-192.png        Ícone do aplicativo
    └── icon-512.png        Ícone do aplicativo
```

---

## Dependências

**Python**

| Pacote | Finalidade |
|---|---|
| Flask | Framework web e servidor HTTP |
| Requests | Cliente HTTP para Nominatim |
| Gunicorn | Servidor WSGI para produção |
| Flexpolyline | Decodificação do formato de polyline da HERE |

**Frontend**

| Biblioteca | Finalidade |
|---|---|
| Leaflet 1.9.4 | Renderização do mapa interativo |
| CartoDB Voyager | Camada de tiles do mapa |
| HERE Routing API v8 | Cálculo de rotas e dados de tráfego |
| HERE Traffic API v7 | Fluxo de trânsito em tempo real |
| Nominatim | Geocodificação reversa durante a navegação GPS |

---

## Instalação

Clone o repositório e instale as dependências Python:

```bash
git clone https://github.com/cassioforza-blip/eleven-maps-v2.git
cd eleven-maps-v2
pip install -r requirements.txt
```

---

## Execução Local

```bash
python app.py
```

O servidor inicia em `http://localhost:5000`. É necessária conexão com a internet para geocodificação, roteamento e carregamento dos tiles do mapa.

---

## Deploy

A aplicação realiza deploy automaticamente no Railway a cada push para o branch `main`. O arquivo `Procfile` define o comando de inicialização:

```
web: gunicorn app:app
```

Nenhuma configuração adicional é necessária no Railway além da conexão com o repositório.

---

## Endpoints da API

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/geocode` | Converte dois endereços em coordenadas geográficas |
| POST | `/calcular` | Retorna estatísticas de tempo e atraso por trânsito |
| POST | `/decodificar` | Decodifica polyline da HERE em array de coordenadas |
| GET | `/sugestoes` | Retorna sugestões de autocomplete de endereço |

---

## Como o Roteamento Funciona

1. O usuário informa um endereço de origem e um de destino.
2. O backend geocodifica ambos os endereços via OpenStreetMap Nominatim.
3. O frontend chama a HERE Routing API v8 com as coordenadas e o modo de transporte selecionado.
4. A polyline retornada é decodificada pelo backend e enviada de volta como array de coordenadas.
5. O frontend consulta a HERE Traffic API para obter dados de velocidade em tempo real ao longo da rota.
6. O backend calcula o tempo estimado de viagem incluindo atrasos por trânsito e paradas em semáforos.
7. A rota é desenhada no mapa com renderização animada.

---

## Navegação GPS

Ao ativar o modo de navegação, a API de Geolocalização do navegador inicia o rastreamento da posição do usuário. A seta direcional é orientada pelo bearing geográfico calculado entre posições GPS consecutivas via fórmula de Haversine, com interpolação angular suave para evitar rotações bruscas. Caso o usuário se desvie mais de 80 metros da rota planejada, a aplicação recalcula automaticamente utilizando as coordenadas GPS atuais como nova origem.

---

## Contexto Acadêmico

Este projeto foi desenvolvido como parte da disciplina de Inteligência Artificial da Universidade Anhanguera — Unidade Mooca, sob orientação do Professor Luiz Antonio.

---

## Referência Bibliográfica

RUSSELL, Stuart J.; NORVIG, Peter. Inteligência artificial: uma abordagem moderna. 4. ed. Rio de Janeiro: GEN LTC, 2022.

---

## Licença

Este projeto tem finalidade acadêmica. Todos os dados de roteamento e tráfego são fornecidos pela HERE Technologies sob plano comercial pago. Os tiles de mapa são fornecidos pela CartoDB e pelos contribuidores do OpenStreetMap sob suas respectivas licenças.
