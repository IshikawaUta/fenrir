import datetime
import pytest
from fenrir import Fenrir, JSONResponse
from fenrir.json import JSONProvider

class CustomJSONProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return '{"custom": true}'
    def loads(self, s, **kwargs):
        return {"custom": True}

@pytest.mark.anyio
async def test_custom_json_provider(app):
    app.json = CustomJSONProvider(app)
    
    @app.get("/json")
    def get_json():
        return {"hello": "world"}

    client = app.test_client()
    resp = await client.get("/json")
    assert resp.status_code == 200
    assert resp.text == '{"custom": true}'

def test_default_json_provider_date_datetime(app):
    dt = datetime.datetime(2026, 5, 20, 15, 0, 0)
    d = datetime.date(2026, 5, 20)
    
    serialized_dt = app.json.dumps(dt)
    serialized_d = app.json.dumps(d)
    
    assert "2026-05-20T15:00:00" in serialized_dt
    assert "2026-05-20" in serialized_d
