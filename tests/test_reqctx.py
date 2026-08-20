from fenrir import request


def test_request_context_isolation(app):
    with app.test_request_context("/one"):
        assert request.path == "/one"
        with app.test_request_context("/two"):
            assert request.path == "/two"
        assert request.path == "/one"
