# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'chatmail relay documentation'
copyright = '2025, chatmail collective'
author = 'chatmail collective'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    #'sphinx.ext.autodoc',
    #'sphinx.ext.viewdoc',
    'sphinx.ext.extlinks',
    'sphinxcontrib.mermaid',
]

templates_path = ['_templates']
exclude_patterns = []

# Repository links go through the roles below.
# CI sets DOC_GITHUB_REF to the head commit of a pull request,
gh_ref = os.environ.get("DOC_GITHUB_REF", "main")

extlinks = {
    "repofile": (f"https://github.com/chatmail/relay/blob/{gh_ref}/%s", "%s"),
    "repodir": (f"https://github.com/chatmail/relay/tree/{gh_ref}/%s", "%s"),
}

# Warn about repository links spelled out in full instead of using the roles.
extlinks_detect_hardcoded_links = True


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
html_css_files = [
    "custom.css",
]

html_title = "chatmail relay documentation"
#html_short_title = f"chatmail-{release}"

html_logo = "_static/chatmail.svg"


