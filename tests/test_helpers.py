import io
import os
import pytest
from fenrir import url_for, send_file, send_from_directory, redirect, Blueprint
from fenrir.exceptions import HTTPNotFound

@pytest.mark.anyio
async def test_url_for(app):
    @app.get("/user/<int:user_id>")
    def user_profile(user_id):
        return f"User {user_id}"

    bp = Blueprint("api", url_prefix="/api")
    @bp.get("/item/<name>")
    def get_item(name):
        return name
    app.register_blueprint(bp)

    with app.test_request_context():
        # Simple route
        assert url_for("user_profile", user_id=42) == "/user/42"
        # Query parameters
        assert url_for("user_profile", user_id=42, page=2) == "/user/42?page=2"
        # Blueprint route
        assert url_for("api.get_item", name="sword") == "/api/item/sword"

@pytest.mark.anyio
async def test_send_file_and_directory(app, tmp_path):
    # Setup test file
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello Helper File")

    @app.get("/file")
    def get_file():
        return send_file(str(test_file))

    @app.get("/dir/<path:filename>")
    def get_from_dir(filename):
        return send_from_directory(str(tmp_path), filename)

    client = app.test_client()

    resp = await client.get("/file")
    assert resp.status_code == 200
    assert resp.text == "Hello Helper File"

    resp = await client.get("/dir/hello.txt")
    assert resp.status_code == 200
    assert resp.text == "Hello Helper File"

    # Traversal test
    with pytest.raises(HTTPNotFound):
        with app.test_request_context():
            send_from_directory(str(tmp_path), "../passwd")

@pytest.mark.anyio
async def test_redirect_helper(app):
    @app.get("/go")
    def go():
        return redirect("/target")

    client = app.test_client()
    resp = await client.get("/go")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/target"
