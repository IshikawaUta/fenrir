import datetime
import uuid

from fenrir.json import TaggedJSONSerializer


def test_tagged_json_serializer():
    serializer = TaggedJSONSerializer()

    dt = datetime.datetime(2026, 5, 20, 15, 0, 0, tzinfo=datetime.timezone.utc)
    d = datetime.date(2026, 5, 20)
    u = uuid.uuid4()
    b = b"hello bytes"
    t = (1, 2, "three")

    data = {
        "datetime": dt,
        "date": d,
        "uuid": u,
        "bytes": b,
        "tuple": t,
    }

    serialized = serializer.dumps(data)
    deserialized = serializer.loads(serialized)

    assert deserialized["datetime"] == dt
    assert deserialized["date"] == d
    assert deserialized["uuid"] == u
    assert deserialized["bytes"] == b
    assert deserialized["tuple"] == t
