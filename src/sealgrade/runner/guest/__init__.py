"""Trusted scripts that run *inside* the strict-tier containers.

They are standard-library-only and shipped as package data so the runtime image can be built from
them and so unit tests can run them without Docker (paths are overridable with environment
variables that the controller never sets inside a container).
"""
