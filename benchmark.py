"""Fenrir vs FastAPI - Benchmark Perbandingan"""
import time
import sys
import asyncio
import statistics
import json
import orjson

# ============================================================
# Benchmark 1: Import Time
# ============================================================
print("=" * 60)
print("1. IMPORT TIME (ms) - Semakin kecil semakin baik")
print("=" * 60)

results = {}

# Fenrir
times = []
for _ in range(3):
    # Clear all fenrir modules
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

winner_import = min(results, key=results.get)
print(f"\n🏆 Pemenang: {winner_import} ({results[winner_import]:.1f}ms)")

# ============================================================
# Benchmark 2: App Initialization Time
# ============================================================
print("\n" + "=" * 60)
print("2. APP INITIALIZATION (ms) - Semakin kecil semakin baik")
print("=" * 60)

results_init = {}

# Fenrir
import fenrir
start = time.perf_counter()
app = fenrir.Fenrir(title='Benchmark')
results_init['Fenrir'] = (time.perf_counter() - start) * 1000
print(f"Fenrir:   {results_init['Fenrir']:.2f}ms")

# FastAPI
from fastapi import FastAPI as FastAPIApp
start = time.perf_counter()
app = FastAPIApp(title='Benchmark')
results_init['FastAPI'] = (time.perf_counter() - start) * 1000
print(f"FastAPI:  {results_init['FastAPI']:.2f}ms")

winner_init = min(results_init, key=results_init.get)
print(f"\n🏆 Pemenang: {winner_init} ({results_init[winner_init]:.2f}ms)")

# ============================================================
# Benchmark 3: Route Registration (100 routes)
# ============================================================
print("\n" + "=" * 60)
print("3. ROUTE REGISTRATION 100 routes (ms) - Semakin kecil semakin baik")
print("=" * 60)

results_route = {}

# Fenrir
app = fenrir.Fenrir(title='Benchmark')
@app.get('/users')
async def get_users():
    return {'users': []}

@app.get('/users/{id}')
async def get_user(id: str):
    return {'user': id}

@app.post('/users')
async def create_user():
    return {'created': True}

start = time.perf_counter()
for i in range(100):
    @app.get(f'/route{i}')
    async def handler(i=i):
        return {'route': i}
results_route['Fenrir'] = (time.perf_counter() - start) * 1000
print(f"Fenrir:   {results_route['Fenrir']:.2f}ms")

# FastAPI
app = FastAPIApp(title='Benchmark')
@app.get('/users')
async def get_users():
    return {'users': []}

@app.get('/users/{id}')
async def get_user(id: str):
    return {'user': id}

@app.post('/users')
async def create_user():
    return {'created': True}

start = time.perf_counter()
for i in range(100):
    @app.get(f'/route{i}')
    async def handler(i=i):
        return {'route': i}
results_route['FastAPI'] = (time.perf_counter() - start) * 1000
print(f"FastAPI:  {results_route['FastAPI']:.2f}ms")

winner_route = min(results_route, key=results_route.get)
print(f"\n🏆 Pemenang: {winner_route} ({results_route[winner_route]:.2f}ms)")

# ============================================================
# Benchmark 4: Request Handling Throughput
# ============================================================
print("\n" + "=" * 60)
print("4. REQUEST HANDLING THROUGHPUT (req/s) - Semakin besar semakin baik")
print("=" * 60)

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

winner_throughput = max(results_throughput, key=results_throughput.get)
print(f"\n🏆 Pemenang: {winner_throughput} ({results_throughput[winner_throughput]:.0f} req/s)")

# ============================================================
# Benchmark 5: JSON Serialization
# ============================================================
print("\n" + "=" * 60)
print("5. JSON SERIALIZATION 10000 ops (ms) - Semakin kecil semakin baik")
print("=" * 60)

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

start = time.perf_counter()
for _ in range(10000):
    orjson.dumps(data)
results_json['orjson'] = (time.perf_counter() - start) * 1000
print(f"orjson:      {results_json['orjson']:.1f}ms")

winner_json = min(results_json, key=results_json.get)
print(f"\n🏆 Pemenang: {winner_json} ({results_json[winner_json]:.1f}ms)")

# ============================================================
# Ringkasan
# ============================================================
print("\n" + "=" * 60)
print("RINGKASAN AKHIR")
print("=" * 60)

print(f"""
| Metrik | Fenrir | FastAPI |
|--------|--------|---------|
| Import (ms) | {results.get('Fenrir', 0):.1f} | {results.get('FastAPI', 0):.1f} |
| App Init (ms) | {results_init.get('Fenrir', 0):.2f} | {results_init.get('FastAPI', 0):.2f} |
| Route Reg 100 (ms) | {results_route.get('Fenrir', 0):.2f} | {results_route.get('FastAPI', 0):.2f} |
| Throughput (req/s) | {results_throughput.get('Fenrir', 0):.0f} | {results_throughput.get('FastAPI', 0):.0f} |
""")

# Score
fenrir_score = 0
fastapi_score = 0

for name, results_dict in [('import', results), ('init', results_init), ('route', results_route), ('throughput', results_throughput)]:
    if name == 'throughput':
        winner = max(results_dict, key=results_dict.get)
    else:
        winner = min(results_dict, key=results_dict.get)
    
    if winner == 'Fenrir':
        fenrir_score += 1
    else:
        fastapi_score += 1

print(f"Skor Akhir:")
print(f"  Fenrir:   {fenrir_score}/4")
print(f"  FastAPI:  {fastapi_score}/4")

if fenrir_score > fastapi_score:
    print(f"\n🏆 Pemenang Overall: FENRIR ({fenrir_score}/4)")
elif fastapi_score > fenrir_score:
    print(f"\n🏆 Pemenang Overall: FASTAPI ({fastapi_score}/4)")
else:
    print(f"\n🤝 SERI ({fenrir_score}/{fastapi_score})")

print("\n" + "=" * 60)
