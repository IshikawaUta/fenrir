from fenrir import Fenrir


def test_instance_path_resolution(tmp_path):
    app = Fenrir(root_path=str(tmp_path), instance_path=str(tmp_path / "custom_instance"))
    assert app.instance_path == str(tmp_path / "custom_instance")

def test_instance_relative_config(tmp_path):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    config_file = instance_dir / "config.py"
    config_file.write_text("DATABASE_URI = 'sqlite:///instance.db'\n")

    app = Fenrir(root_path=str(tmp_path), instance_relative_config=True)
    app.config.from_pyfile("config.py")
    assert app.config["DATABASE_URI"] == "sqlite:///instance.db"
