default:
    just --list

fmt:
    #! /usr/bin/env nix-shell
    #! nix-shell -i sh -p ruff
    ruff check --fix --select I
    ruff format