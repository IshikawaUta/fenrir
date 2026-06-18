import pytest
from unittest import mock
import sys
import os
from fenrir.cli import main

# Mock app target for testing
class MockApp:
    title = "Test App"
    version = "0.0.1"
    openapi_url = "/openapi.json"
    _route_blueprints = {}
    
    class Router:
        routes = []
    router = Router()
    
    def run(self, **kwargs):
        pass


@pytest.fixture
def mock_load_app():
    with mock.patch("fenrir.cli.load_app", return_value=MockApp()) as m:
        yield m


def test_cli_help(capsys):
    with mock.patch("sys.argv", ["fenrir", "--help"]):
        with pytest.raises(SystemExit):
            main()
    captured = capsys.readouterr()
    assert "Fenrir CLI" in captured.out or "subcommands" in captured.out


def test_cli_version(capsys):
    with mock.patch("sys.argv", ["fenrir", "-v"]):
        with pytest.raises(SystemExit):
            main()
    captured = capsys.readouterr()
    # Argparse prints version to stdout or stderr depending on Python version
    output = captured.out or captured.err
    assert "Fenrir Web Framework" in output
    assert "Version" in output



def test_cli_routes(mock_load_app, capsys):
    # Setup mock routes on MockApp
    class MockRoute:
        path_pattern = "/test"
        methods = ["GET"]
        handler = lambda: None
        def is_falcon_resource(self): return False

    MockApp.router.routes = [MockRoute()]
    
    with mock.patch("sys.argv", ["fenrir", "routes", "mock_module:app"]):
        main()
    captured = capsys.readouterr()
    assert "Path" in captured.out
    assert "Methods" in captured.out
    mock_load_app.assert_called_once_with("mock_module:app")


def test_cli_shell(mock_load_app):
    with mock.patch("sys.argv", ["fenrir", "shell", "mock_module:app"]):
        with mock.patch("code.interact") as mock_interact:
            main()
            mock_interact.assert_called_once()
            banner, local_vars = mock_interact.call_args[1].values()
            assert "Fenrir" in banner
            assert "app" in local_vars


def test_cli_run(mock_load_app):
    app = MockApp()
    mock_arbiter = mock.MagicMock()
    with mock.patch("fenrir.cli.load_app", return_value=app):
        with mock.patch("asteri.arbiter.Arbiter", return_value=mock_arbiter):
            with mock.patch("sys.argv", ["fenrir", "run", "mock_module:app", "-p", "8888", "--dev"]):
                main()
                mock_arbiter.start.assert_called_once()
    os.environ.pop("FENRIR_DEV_MODE", None)


def test_cli_run_dev_sets_env_var(mock_load_app):
    """Test that --dev flag sets FENRIR_DEV_MODE env var."""
    app = MockApp()
    mock_arbiter = mock.MagicMock()
    os.environ.pop("FENRIR_DEV_MODE", None)

    with mock.patch("fenrir.cli.load_app", return_value=app):
        with mock.patch("asteri.arbiter.Arbiter", return_value=mock_arbiter):
            with mock.patch("sys.argv", ["fenrir", "run", "mock_module:app", "--dev"]):
                main()
                assert os.environ.get("FENRIR_DEV_MODE") == "1"
                assert app.dev_mode is True
    os.environ.pop("FENRIR_DEV_MODE", None)


def test_cli_run_no_dev_no_env_var(mock_load_app):
    """Test that running without --dev does not set FENRIR_DEV_MODE."""
    app = MockApp()
    mock_arbiter = mock.MagicMock()
    os.environ.pop("FENRIR_DEV_MODE", None)

    with mock.patch("fenrir.cli.load_app", return_value=app):
        with mock.patch("asteri.arbiter.Arbiter", return_value=mock_arbiter):
            with mock.patch("sys.argv", ["fenrir", "run", "mock_module:app"]):
                main()
                assert "FENRIR_DEV_MODE" not in os.environ
    os.environ.pop("FENRIR_DEV_MODE", None)


def test_cli_bench(mock_load_app):
    # Mock httpx AsyncClient in bench
    with mock.patch("sys.argv", ["fenrir", "bench", "mock_module:app", "-i", "10", "-t", "2"]):
        with mock.patch("httpx.AsyncClient") as mock_client:
            # Setup mock client to handle request
            client_instance = mock_client.return_value.__aenter__.return_value
            client_instance.request = mock.AsyncMock()
            
            main()
            
            # Should call client.request at least 50 (warmup) + 20 (trials) times
            assert client_instance.request.call_count >= 70


def test_cli_new(tmp_path):
    import os
    target_dir = tmp_path / "my_new_app"
    with mock.patch("sys.argv", ["fenrir", "new", str(target_dir)]):
        main()
    
    assert os.path.exists(target_dir)
    assert os.path.exists(target_dir / "app.py")
    assert os.path.exists(target_dir / "static" / "style.css")
    assert os.path.exists(target_dir / "templates" / "index.html")
    assert os.path.exists(target_dir / "logo.png")
    assert os.path.exists(target_dir / "favicon.ico")
    assert os.path.exists(target_dir / "requirements.txt")


def test_cli_info(mock_load_app, capsys):
    with mock.patch("sys.argv", ["fenrir", "info", "mock_module:app"]):
        main()
    captured = capsys.readouterr()
    assert "SYSTEM ENVIRONMENT" in captured.out
    assert "APPLICATION DETAILS" in captured.out
    assert "Fenrir version" in captured.out

