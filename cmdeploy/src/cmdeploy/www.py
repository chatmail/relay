import hashlib
import importlib.resources
import time
import traceback
import webbrowser

import markdown
from chatmaild.config import read_config
from jinja2 import Template

from .genqr import gen_qr_png_data

LANGUAGE_NAMES = {
    "EN": " 🇬🇧 English",
    "RU": " 🇷🇺 Русский",
    # "UA": "Українська",
    # "FR": "Français",
    # "DE": "Deutsch",
}

def snapshot_dir_stats(somedir):
    d = {}
    for path in somedir.iterdir():
        if path.is_file() and path.name[0] != "." and path.suffix != ".swp":
            mtime = path.stat().st_mtime
            hash = hashlib.md5(path.read_bytes()).hexdigest()
            d[path] = (mtime, hash)
    return d


def prepare_template(source, locales_dir, languages=["EN"]):
    assert source.exists(), f"Template {source} not found."
    assert locales_dir.exists(), f"Locales directory {locales_dir} not found."
    base_name = source.stem
    render_vars = {
        "pagename": "home" if base_name == "index" else base_name
    }

    selected_langs = (
        sorted([d.name.upper() for d in locales_dir.iterdir() if d.is_dir()])
        if "ALL" in [l.upper() for l in languages]
        else [l.upper() for l in languages]
    )
    
    markdown_blocks = []
    
    for lang_code in selected_langs:
        lang_folder = locales_dir / lang_code
        lang_file = lang_folder / f"{base_name}.md"
        lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)

        if lang_file.exists():
            content = lang_file.read_text().strip()
        else:
            print(f"[WARNING]: Missing file {lang_file}. Inserting fallback message.")
            content = "Content for this language is not available, please contact your server administrator."

        markdown_blocks.append(f"/// tab | {lang_name}\n{content}\n///")

    if not markdown_blocks:
        print("[WARNING] No valid language content found. Skipping file.")
        return None, None

    original_markdown = source.read_text()
    combined_markdown = original_markdown.replace("Temporal content", "\n\n".join(markdown_blocks))

    render_vars["markdown_html"] = markdown.markdown(
        combined_markdown,
        extensions=["pymdownx.blocks.tab"]
    )
    
    page_layout_path = source.with_name("page-layout.html")
    assert page_layout_path.exists(), f"Missing template: {page_layout_path}"
    page_layout = page_layout_path.read_text()

    return render_vars, page_layout


def build_webpages(src_dir, build_dir, config):
    try:
        _build_webpages(src_dir, build_dir, config)
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
    languages = config.languages
    assert src_dir.exists(), src_dir
    if not build_dir.exists():
        build_dir.mkdir()

    qr_path = build_dir.joinpath(f"qr-chatmail-invite-{mail_domain}.png")
    qr_path.write_bytes(gen_qr_png_data(mail_domain).read())
    
    locales_dir = src_dir / "locales"

    for path in src_dir.iterdir():
        if path.suffix == ".md":
            render_vars, content = prepare_template(path, locales_dir, languages)

            if render_vars is None:
                continue

            render_vars["username_min_length"] = int_to_english(config.username_min_length)
            render_vars["username_max_length"] = int_to_english(config.username_max_length)
            render_vars["password_min_length"] = int_to_english(config.password_min_length)

            target = build_dir.joinpath(path.stem + ".html")

            # recursive jinja2 rendering
            while True:
                new = Template(content).render(config=config, **render_vars)
                if new == content:
                    break
                content = new

            with target.open("w") as f:
                f.write(content)

        elif path.name != "page-layout.html" and path.name != "locales":
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
    www_path = reporoot.joinpath("www")
    src_path = www_path.joinpath("src")
    stats = None
    build_dir = www_path.joinpath("build")
    src_dir = www_path.joinpath("src")
    index_path = build_dir.joinpath("index.html")

    # start web page generation, open a browser and wait for changes
    build_webpages(src_dir, build_dir, config)
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
        build_webpages(src_dir, build_dir, config)
        print(f"[{changenum}] regenerated web pages at: {index_path}")
        print(f"URL: file://{index_path.resolve()}\n\n")
        count = 0


if __name__ == "__main__":
    main()
