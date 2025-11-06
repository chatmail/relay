

## Building the documentation 

You can use the `make` command and `make html` to build web pages. 

You need a Python environment where the following install was excuted: 

    pip install sphinx-build furo sphinx-autobuild 

To develop/change documentation, you can then do: 

    make auto 

A page will open at https://127.0.0.1:8000/ serving the docs and it will 
react to changes to source files pretty fast. 

