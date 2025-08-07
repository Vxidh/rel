from django.urls import re_path
from .consumers import RemoteControlConsumer

websocket_urlpatterns = [
    re_path(r"ws/remote-control/(?P<node_id>[A-Za-z0-9_-]+)/", RemoteControlConsumer.as_asgi()),
]
