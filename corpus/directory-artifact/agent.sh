#!/bin/bash
# Hostile agent action: make the declared artifact a directory.
mkdir "/work/$SG_ARTIFACT"
echo "x = 1" > "/work/$SG_ARTIFACT/inner.py"
