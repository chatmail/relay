
# Chatmail relays for end-to-end encrypted email

Chatmail relay servers are interoperable Mail Transport Agents (MTAs) designed for: 

-  **Zero State:** no private data or metadata collected, messages are auto-deleted, low disk usage

-  **Instant/Realtime:** sub-second message delivery, realtime P2P
   streaming, privacy-preserving Push Notifications for Apple, Google, and Huawei;

-  **Security Enforcement**: only strict TLS, DKIM and OpenPGP with minimized metadata accepted

-  **Reliable Federation and Decentralization:** No spam or IP reputation checks, federating
   depends on established IETF standards and protocols.

This repository contains everything needed to setup a ready-to-use chatmail relay on an ssh-reachable host. 
For getting started and more information please refer to the web version of this repositories' documentation at

[https://chatmail.at/doc/relay](https://chatmail.at/doc/relay)

# Notes on Nixos

To develop, deploy or generate the documentation in Nixos, you need to run `nix-shell` on the project folder. 
That would install a local Python virtual environment that just works. 
Otherwise you'll miss `sphinxcontrib.mermaid` dependency, not available in Nixpkg or some special C library. 


## Building the documentation 

You can use the `make` command and `make html` to build web pages. 

You need a Python environment where the following install was excuted: 

    pip install sphinx-build furo sphinx-autobuild 

To develop/change documentation, you can then do: 

    make auto 

A page will open at https://127.0.0.1:8000/ serving the docs and it will 
react to changes to source files pretty fast. 