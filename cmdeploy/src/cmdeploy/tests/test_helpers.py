from pathlib import Path

from cmdeploy.www import build_webpages


def test_build_webpages(tmp_path, make_config):
    src_dir = (Path(__file__).resolve() / "../../../../../www/src").resolve()
    assert src_dir.exists(), src_dir
    config = make_config("chat.example.org")
    build_dir = tmp_path.joinpath("build")
    build_webpages(src_dir, build_dir, config)
    assert len([x for x in build_dir.iterdir() if x.suffix == ".html"]) >= 3
