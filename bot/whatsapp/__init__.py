"""CalTrack on WhatsApp (2026-10-15).

TARS's wa-gateway (same box) forwards the "CalTrack" WhatsApp group here and
sends our replies back. The Telegram handlers run unchanged: shim.py gives
them Telegram-shaped objects whose replies go to WhatsApp, and inline
keyboards become WhatsApp polls. Telegram keeps working in parallel.
"""
