import pytest
from fenrir import Fenrir, request

class CustomRequest:
    def __init__(self, scope):
        self.scope = scope
        self.path = scope.get("path", "/")
        self.session = None

def test_request_subclassing(app):
    # Swap out request class if customized
    # Verify that request proxy correctly delegates
    with app.test_request_context("/subclass"):
        assert request.path == "/subclass"
