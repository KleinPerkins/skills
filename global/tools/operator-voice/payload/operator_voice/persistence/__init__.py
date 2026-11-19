"""Persistence — build plan v3 §4: encrypted local SQLite/WAL for every operator, plus an
optional ``ENCRYPTED_GIT`` profile-pack replica. See ``crypto.py`` for the envelope-encryption
design (KEK in OS Keychain, per-generation DEK wrapped by the KEK, erasure = destroy + rewrap).
"""
