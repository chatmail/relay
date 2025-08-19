import hashlib
import importlib.resources
import time
import traceback
import webbrowser
from pathlib import Path

import markdown
from chatmaild.config import read_config
from jinja2 import Template

from .genqr import gen_qr_png_data


def snapshot_dir_stats(somedir):
    d = {}
    for path in somedir.iterdir():
        if path.is_file() and path.name[0] != "." and path.suffix != ".swp":
            mtime = path.stat().st_mtime
            hash = hashlib.md5(path.read_bytes()).hexdigest()
            d[path] = (mtime, hash)
    return d


def prepare_template(source):
    assert source.exists(), source
    render_vars = {}
    render_vars["pagename"] = "home" if source.stem == "index" else source.stem
    render_vars["markdown_html"] = markdown.markdown(source.read_text())
    page_layout = source.with_name("page-layout.html").read_text()
    return render_vars, page_layout


def get_paths(config) -> (Path, Path, Path):
    reporoot = importlib.resources.files(__package__).joinpath("../../../").resolve()
    www_path = Path(config.www_folder)
    # if www_folder was not set, use default directory
    if config.www_folder == "":
        www_path = reporoot.joinpath("www")
    src_dir = www_path.joinpath("src")
    # if www_folder is a hugo page, build it
    if src_dir.joinpath("index.md").is_file():
        build_dir = www_path.joinpath("build")
    # if it is not a hugo page, upload it as is
    else:
        build_dir = None
    return www_path, src_dir, build_dir


def build_webpages(src_dir, build_dir, config) -> Path:
    try:
        return _build_webpages(src_dir, build_dir, config)
    except Exception:
        print(traceback.format_exc())


def int_to_english(number):
    if number >= 0 and number <= 12:
        a = [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
        ]
        return a[number]
    elif number <= 50:
        return str(number)
    if number > 50:
        return "more"


def _build_webpages(src_dir, build_dir, config):
    mail_domain = config.mail_domain
    assert src_dir.exists(), src_dir
    if not build_dir.exists():
        build_dir.mkdir()

    qr_path = build_dir.joinpath(f"qr-chatmail-invite-{mail_domain}.png")
    qr_path.write_bytes(gen_qr_png_data(mail_domain).read())

    for path in src_dir.iterdir():
        if path.suffix == ".md":
            render_vars, content = prepare_template(path)
            render_vars["username_min_length"] = int_to_english(
                config.username_min_length
            )
            render_vars["username_max_length"] = int_to_english(
                config.username_max_length
            )
            render_vars["password_min_length"] = int_to_english(
                config.password_min_length
            )
            target = build_dir.joinpath(path.stem + ".html")

            # recursive jinja2 rendering
            while 1:
                new = Template(content).render(config=config, **render_vars)
                if new == content:
                    break
                content = new

            with target.open("w") as f:
                f.write(content)
        elif path.name != "page-layout.html":
            target = build_dir.joinpath(path.name)
            target.write_bytes(path.read_bytes())
    return build_dir


def main():
    path = importlib.resources.files(__package__)
    reporoot = path.joinpath("../../../").resolve()
    inipath = reporoot.joinpath("chatmail.ini")
    config = read_config(inipath)
    config.webdev = True
    assert config.mail_domain

    # start web page generation, open a browser and wait for changes
    www_path, src_path, build_dir = get_paths(config)
    build_dir = build_webpages(src_path, build_dir, config)
    index_path = build_dir.joinpath("index.html")
    webbrowser.open(str(index_path))
    stats = snapshot_dir_stats(src_path)
    print(f"\nOpened URL: file://{index_path.resolve()}\n")
    print(f"watching {src_path} directory for changes")

    changenum = 0
    count = 0
    while True:
        newstats = snapshot_dir_stats(src_path)
        if newstats == stats and count % 60 != 0:
            count += 1
            time.sleep(1.0)
            continue

        for key in newstats:
            if stats[key] != newstats[key]:
                print(f"*** CHANGED: {key}")
                changenum += 1

        stats = newstats
        build_webpages(src_path, build_dir, config)
        print(f"[{changenum}] regenerated web pages at: {index_path}")
        print(f"URL: file://{index_path.resolve()}\n\n")
        count = 0


if __name__ == "__main__":
    main()
