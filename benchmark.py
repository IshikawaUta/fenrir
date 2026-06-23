"""Fenrir vs FastAPI vs Flask vs Falcon vs Sanic - Benchmark Perbandingan"""
import time
import sys
import asyncio
import statistics
import json
import os

# ============================================================
# Benchmark 1: Import Time
# ============================================================
print("=" * 70)
print("1. IMPORT TIME (ms) - Semakin kecil semakin baik")
print("=" * 70)

results = {}

# Fenrir
times = []
for _ in range(3):
    mods_to_remove = [k for k in sys.modules if k.startswith('fenrir')]
    for m in mods_to_remove:
        del sys.modules[m]
    start = time.perf_counter()
    import fenrir
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)
results['Fenrir'] = statistics.mean(times)
print(f"Fenrir:   {results['Fenrir']:.1f}ms")

# FastAPI
times = []
for _ in range(3):
    mods_to_remove = [k for k in sys.modules if k.startswith('fastapi')]
    for m in mods_to_remove:
        del sys.modules[m]
    start = time.perf_counter()
    from fastapi import FastAPI
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)
results['FastAPI'] = statistics.mean(times)
print(f"FastAPI:  {results['FastAPI']:.1f}ms")

# Flask
times = []
for _ in range(3):
    mods_to_remove = [k for k in sys.modules if k.startswith('flask')]
    for m in mods_to_remove:
        del sys.modules[m]
    start = time.perf_counter()
    from flask import Flask
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)
results['Flask'] = statistics.mean(times)
print(f"Flask:    {results['Flask']:.1f}ms")

# Falcon
times = []
for _ in range(3):
    mods_to_remove = [k for k in sys.modules if k.startswith('falcon')]
    for m in mods_to_remove:
        del sys.modules[m]
    start = time.perf_counter()
    import falcon
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)
results['Falcon'] = statistics.mean(times)
print(f"Falcon:   {results['Falcon']:.1f}ms")

# Sanic
times = []
for _ in range(3):
    mods_to_remove = [k for k in sys.modules if k.startswith('sanic')]
    for m in mods_to_remove:
        del sys.modules[m]
    start = time.perf_counter()
    from sanic import Sanic
    elapsed = (time.perf_counter() - start) * 1000
    times.append(elapsed)
results['Sanic'] = statistics.mean(times)
print(f"Sanic:    {results['Sanic']:.1f}ms")

winner_import = min(results, key=results.get)
print(f"\n🏆 Pemenang: {winner_import} ({results[winner_import]:.1f}ms)")

# ============================================================
# Benchmark 2: App Initialization Time
# ============================================================
print("\n" + "=" * 70)
print("2. APP INITIALIZATION (ms) - Semakin kecil semakin baik")
print("=" * 70)

results_init = {}

import fenrir
start = time.perf_counter()
app = fenrir.Fenrir(title='Benchmark')
results_init['Fenrir'] = (time.perf_counter() - start) * 1000
print(f"Fenrir:   {results_init['Fenrir']:.2f}ms")

from fastapi import FastAPI as FastAPIApp
start = time.perf_counter()
app = FastAPIApp(title='Benchmark')
results_init['FastAPI'] = (time.perf_counter() - start) * 1000
print(f"FastAPI:  {results_init['FastAPI']:.2f}ms")

from flask import Flask as FlaskApp
start = time.perf_counter()
app = FlaskApp(__name__)
results_init['Flask'] = (time.perf_counter() - start) * 1000
print(f"Flask:    {results_init['Flask']:.2f}ms")

import falcon
start = time.perf_counter()
app = falcon.App()
results_init['Falcon'] = (time.perf_counter() - start) * 1000
print(f"Falcon:   {results_init['Falcon']:.2f}ms")

from sanic import Sanic as SanicApp
Sanic._app_registry.clear()
start = time.perf_counter()
app = SanicApp("Benchmark")
results_init['Sanic'] = (time.perf_counter() - start) * 1000
print(f"Sanic:    {results_init['Sanic']:.2f}ms")

winner_init = min(results_init, key=results_init.get)
print(f"\n🏆 Pemenang: {winner_init} ({results_init[winner_init]:.2f}ms)")

# ============================================================
# Benchmark 3: Route Registration (100 routes)
# ============================================================
print("\n" + "=" * 70)
print("3. ROUTE REGISTRATION 100 routes (ms) - Semakin kecil semakin baik")
print("=" * 70)

results_route = {}

# Fenrir
app = fenrir.Fenrir(title='Benchmark')

start = time.perf_counter()
for i in range(100):
    @app.get(f'/route{i}')
    async def handler(i=i):
        return {'route': i}
results_route['Fenrir'] = (time.perf_counter() - start) * 1000
print(f"Fenrir:   {results_route['Fenrir']:.2f}ms")

# FastAPI
app = FastAPIApp(title='Benchmark')

start = time.perf_counter()
for i in range(100):
    @app.get(f'/route{i}')
    async def handler(i=i):
        return {'route': i}
results_route['FastAPI'] = (time.perf_counter() - start) * 1000
print(f"FastAPI:  {results_route['FastAPI']:.2f}ms")

# Flask
app = FlaskApp(__name__)

start = time.perf_counter()
for i in range(100):
    def make_handler(rid):
        def handler():
            return {'route': rid}
        return handler
    app.add_url_rule(f'/route{i}', f'route{i}', make_handler(i))
results_route['Flask'] = (time.perf_counter() - start) * 1000
print(f"Flask:    {results_route['Flask']:.2f}ms")

# Falcon
app = falcon.App()

class GenericResource:
    def __init__(self, route_id):
        self.route_id = route_id
    def on_get(self, req, resp):
        resp.media = {'route': self.route_id}

start = time.perf_counter()
for i in range(100):
    app.add_route(f'/route{i}', GenericResource(i))
results_route['Falcon'] = (time.perf_counter() - start) * 1000
print(f"Falcon:   {results_route['Falcon']:.2f}ms")

# Sanic
Sanic._app_registry.clear()
app = SanicApp("Benchmark")

start = time.perf_counter()
for i in range(100):
    @app.get(f'/route{i}')
    async def handler(request, i=i):
        return {'route': i}
results_route['Sanic'] = (time.perf_counter() - start) * 1000
print(f"Sanic:    {results_route['Sanic']:.2f}ms")

winner_route = min(results_route, key=results_route.get)
print(f"\n🏆 Pemenang: {winner_route} ({results_route[winner_route]:.2f}ms)")

# ============================================================
# Benchmark 4: Request Handling Throughput
# ============================================================
print("\n" + "=" * 70)
print("4. REQUEST HANDLING THROUGHPUT (req/s) - Semakin besar semakin baik")
print("=" * 70)

results_throughput = {}

# Fenrir
async def bench_fenrir():
    from fenrir.testing import TestClient
    app = fenrir.Fenrir(title='Benchmark')

    @app.get('/hello')
    async def hello():
        return {'message': 'Hello, World!'}

    @app.get('/users/{id}')
    async def get_user(id: str):
        return {'user': id}

    @app.post('/users')
    async def create_user():
        return {'created': True}

    async with TestClient(app) as client:
        start = time.perf_counter()
        for _ in range(1000):
            await client.get('/hello')
            await client.get('/users/123')
            await client.post('/users')
        elapsed = time.perf_counter() - start
        return 3000 / elapsed

results_throughput['Fenrir'] = asyncio.run(bench_fenrir())
print(f"Fenrir:   {results_throughput['Fenrir']:.0f} req/s")

# FastAPI
async def bench_fastapi():
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport

    app = FastAPI(title='Benchmark')

    @app.get('/hello')
    async def hello():
        return {'message': 'Hello, World!'}

    @app.get('/users/{id}')
    async def get_user(id: str):
        return {'user': id}

    @app.post('/users')
    async def create_user():
        return {'created': True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        start = time.perf_counter()
        for _ in range(1000):
            await client.get('/hello')
            await client.get('/users/123')
            await client.post('/users')
        elapsed = time.perf_counter() - start
        return 3000 / elapsed

results_throughput['FastAPI'] = asyncio.run(bench_fastapi())
print(f"FastAPI:  {results_throughput['FastAPI']:.0f} req/s")

# Flask (sync, use test client)
def bench_flask():
    from flask import Flask, jsonify, request as flask_request

    app = Flask(__name__)

    @app.route('/hello')
    def hello():
        return jsonify({'message': 'Hello, World!'})

    @app.route('/users/<id>')
    def get_user(id):
        return jsonify({'user': id})

    @app.route('/users', methods=['POST'])
    def create_user():
        return jsonify({'created': True})

    with app.test_client() as client:
        start = time.perf_counter()
        for _ in range(1000):
            client.get('/hello')
            client.get('/users/123')
            client.post('/users')
        elapsed = time.perf_counter() - start
        return 3000 / elapsed

results_throughput['Flask'] = bench_flask()
print(f"Flask:    {results_throughput['Flask']:.0f} req/s")

# Falcon (sync, use test client)
def bench_falcon():
    import falcon
    import falcon.testing

    class HelloResource:
        def on_get(self, req, resp):
            resp.media = {'message': 'Hello, World!'}

    class UserResource:
        def on_get(self, req, resp, user_id):
            resp.media = {'user': user_id}

    class UserListResource:
        def on_post(self, req, resp):
            resp.media = {'created': True}

    app = falcon.App()
    app.add_route('/hello', HelloResource())
    app.add_route('/users/{user_id}', UserResource())
    app.add_route('/users', UserListResource())

    client = falcon.testing.TestClient(app)
    start = time.perf_counter()
    for _ in range(1000):
        client.simulate_get('/hello')
        client.simulate_get('/users/123')
        client.simulate_post('/users')
    elapsed = time.perf_counter() - start
    return 3000 / elapsed

results_throughput['Falcon'] = bench_falcon()
print(f"Falcon:   {results_throughput['Falcon']:.0f} req/s")

# Sanic (async)
async def bench_sanic():
    from sanic import Sanic
    from sanic_testing import TestManager
    from sanic.response import json as sanic_json

    Sanic._app_registry.clear()
    app = Sanic("Benchmark")
    TestManager(app)

    @app.get('/hello')
    async def hello(request):
        return sanic_json({'message': 'Hello, World!'})

    @app.get('/users/<id>')
    async def get_user(request, id):
        return sanic_json({'user': id})

    @app.post('/users')
    async def create_user(request):
        return sanic_json({'created': True})

    _, resp = await app.asgi_client.get('/hello')
    start = time.perf_counter()
    for _ in range(1000):
        await app.asgi_client.get('/hello')
        await app.asgi_client.get('/users/123')
        await app.asgi_client.post('/users')
    elapsed = time.perf_counter() - start
    return 3000 / elapsed

try:
    results_throughput['Sanic'] = asyncio.run(bench_sanic())
    print(f"Sanic:    {results_throughput['Sanic']:.0f} req/s")
except Exception as e:
    print(f"Sanic:    SKIP ({e})")
    results_throughput['Sanic'] = 0

winner_throughput = max(results_throughput, key=results_throughput.get)
print(f"\n🏆 Pemenang: {winner_throughput} ({results_throughput[winner_throughput]:.0f} req/s)")

# ============================================================
# Benchmark 5: JSON Serialization
# ============================================================
print("\n" + "=" * 70)
print("5. JSON SERIALIZATION 10000 ops (ms) - Semakin kecil semakin baik")
print("=" * 70)

data = {
    'users': [
        {'id': i, 'name': f'User {i}', 'email': f'user{i}@example.com', 'active': True}
        for i in range(100)
    ]
}

results_json = {}

start = time.perf_counter()
for _ in range(10000):
    json.dumps(data)
results_json['json'] = (time.perf_counter() - start) * 1000
print(f"stdlib json: {results_json['json']:.1f}ms")

try:
    import orjson
    start = time.perf_counter()
    for _ in range(10000):
        orjson.dumps(data)
    results_json['orjson'] = (time.perf_counter() - start) * 1000
    print(f"orjson:      {results_json['orjson']:.1f}ms")
except ImportError:
    results_json['orjson'] = results_json['json']
    print(f"orjson:      not installed")

winner_json = min(results_json, key=results_json.get)
print(f"\n🏆 Pemenang: {winner_json} ({results_json[winner_json]:.1f}ms)")

# ============================================================
# Ringkasan
# ============================================================
print("\n" + "=" * 70)
print("RINGKASAN AKHIR")
print("=" * 70)

frameworks = ['Fenrir', 'FastAPI', 'Flask', 'Falcon', 'Sanic']

print(f"\n{'Metrik':<25} {'Fenrir':>10} {'FastAPI':>10} {'Flask':>10} {'Falcon':>10} {'Sanic':>10}")
print("-" * 75)
print(f"{'Import (ms)':<25} {results.get('Fenrir', 0):>10.1f} {results.get('FastAPI', 0):>10.1f} {results.get('Flask', 0):>10.1f} {results.get('Falcon', 0):>10.1f} {results.get('Sanic', 0):>10.1f}")
print(f"{'App Init (ms)':<25} {results_init.get('Fenrir', 0):>10.2f} {results_init.get('FastAPI', 0):>10.2f} {results_init.get('Flask', 0):>10.2f} {results_init.get('Falcon', 0):>10.2f} {results_init.get('Sanic', 0):>10.2f}")
print(f"{'Route Reg 100 (ms)':<25} {results_route.get('Fenrir', 0):>10.2f} {results_route.get('FastAPI', 0):>10.2f} {results_route.get('Flask', 0):>10.2f} {results_route.get('Falcon', 0):>10.2f} {results_route.get('Sanic', 0):>10.2f}")
print(f"{'Throughput (req/s)':<25} {results_throughput.get('Fenrir', 0):>10.0f} {results_throughput.get('FastAPI', 0):>10.0f} {results_throughput.get('Flask', 0):>10.0f} {results_throughput.get('Falcon', 0):>10.0f} {results_throughput.get('Sanic', 0):>10.0f}")

# Score per category
print(f"\n🏆 Pemenang per Kategori:")
categories = [
    ('Import', results, 'min'),
    ('App Init', results_init, 'min'),
    ('Route Registration', results_route, 'min'),
    ('Throughput', results_throughput, 'max'),
    ('JSON Serialization', results_json, 'min'),
]

scores = {f: 0 for f in frameworks}
for cat_name, cat_results, mode in categories:
    if mode == 'min':
        winner = min(cat_results, key=cat_results.get)
    else:
        winner = max(cat_results, key=cat_results.get)
    if winner in scores:
        scores[winner] += 1
    print(f"  {cat_name:<25} → {winner}")

print(f"\n📊 Skor Akhir:")
for name, score in sorted(scores.items(), key=lambda x: -x[1]):
    bar = "█" * score
    print(f"  {name:<10} {score}/5  {bar}")

overall_winner = max(scores, key=scores.get)
print(f"\n🏆 Pemenang Overall: {overall_winner.upper()} ({scores[overall_winner]}/5)")

print("\n" + "=" * 70)
