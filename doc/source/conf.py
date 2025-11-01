# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

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
    'sphinxcontrib.mermaid',
]

templates_path = ['_templates']
exclude_patterns = []



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


