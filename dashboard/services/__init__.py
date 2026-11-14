"""Dashboard application services: everything the HTTP and WebSocket layer calls.

Routes stay thin and call into these; these never run database, inference or
audio work themselves. They reach the engine only through the bus.
"""
