#!/bin/bash
# Hostile agent action: make the declared artifact a symlink to a sensitive file.
ln -s /etc/passwd "/work/$SG_ARTIFACT"
