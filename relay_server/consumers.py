# File: relay_server/consumers.py

import json
import logging
import asyncio
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from oauth2_provider.models import AccessToken
from django.utils.timezone import now
from datetime import datetime
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async

User = get_user_model()
logger = logging.getLogger(__name__)

# Central state stores
req_resp = {}
nodes_available = {}
node_connections = {}

CLEANUP_INTERVAL_MINUTES = 60

class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

@database_sync_to_async
def get_token_and_user(token):
    token_obj = AccessToken.objects.select_related("user").get(token=token)
    if token_obj.is_expired():
        raise ValueError("Token expired")
    return token_obj

class NodeConsumer(AsyncWebsocketConsumer):
    cleanup_started = False
    json_encoder_class = CustomJsonEncoder

    async def connect(self):
        self.node_id = self.scope['url_route']['kwargs']['node_id']
        headers = dict(self.scope['headers'])
        auth_header = headers.get(b'authorization')
        if not auth_header:
            logger.warning("Missing Authorization header.")
            await self.close(code=4001)
            return
        try:
            token_type, access_token = auth_header.decode().split()
            if token_type.lower() != 'bearer':
                raise ValueError("Authorization header is not Bearer")
            token_obj = await get_token_and_user(access_token)
            self.scope["user"] = token_obj.user
        except Exception as e:
            logger.exception("WebSocket token validation failed.")
            await self.close(code=4003)
            return
        if self.node_id in nodes_available:
            logger.warning(f"Duplicate connection for node_id {self.node_id}. Rejecting.")
            await self.close()
            return
        nodes_available[self.node_id] = self
        self.metadata = { "node_id": self.node_id, "connected_to": None, "last_pinged": timezone.now(), "client_user": self.scope["user"].username }
        if not NodeConsumer.cleanup_started:
            asyncio.create_task(cleanup_commands())
            NodeConsumer.cleanup_started = True
        await self.accept()
        logger.info(f"RPA Node {self.node_id} connected and authenticated.")

    async def disconnect(self, close_code):
        nodes_available.pop(self.node_id, None)
        node_connections.pop(self.node_id, None)
        logger.info(f"WebSocket disconnected for node {self.node_id} with code {close_code}.")

    async def send_command_to_node(self, request_id, request_data):
        req_resp[(self.node_id, request_id)] = [request_data]
        command = { "type": "command", "command": request_data }
        await self.send(text_data=json.dumps(command))
        logger.info(f"Command sent to node {self.node_id} Req ID: {request_id}")

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data: return
        try:
            message = json.loads(text_data)
            msg_type = message.get('type')
            request_id = message.get('requestId') or message.get('response', {}).get('requestId')
            logger.info(f"Received message type '{msg_type}' from {self.node_id} (Req ID: {request_id})")

            if msg_type == 'node_response':
                response = message.get('response', {})
                req_id = response.get('requestId')
                if req_id:
                    req_resp.setdefault((self.node_id, req_id), [{}, {}])[1] = response
                    logger.info(f"Updated command status for {req_id}.")
            elif msg_type == 'image_frame':
                frame_data_base64 = message.get("frame_data")
                if not frame_data_base64:
                    logger.warning(f"Missing frame_data in image_frame from node {self.node_id}")
                    return
                controller_consumer = node_connections.get(self.node_id)
                if controller_consumer:
                    try:
                        # Directly call the specific method on the controller's consumer instance
                        await controller_consumer.send_image_frame(frame_data_base64)
                        logger.info(f"Forwarded image_frame from node {self.node_id} to controller.")
                    except Exception as e:
                        logger.exception(f"Failed to forward image_frame from {self.node_id}: {e}")
                else:
                    logger.warning(f"No controller attached to node {self.node_id}; dropped image_frame.")
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        except Exception as e:
            logger.exception(f"Error in receive() from {self.node_id}: {e}")

async def cleanup_commands():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        cutoff = timezone.now() - timezone.timedelta(minutes=CLEANUP_INTERVAL_MINUTES)
        for key, data in list(req_resp.items()):
            timestamp = data[0].get('timestamp', 0)
            if datetime.fromtimestamp(timestamp) < cutoff:
                del req_resp[key]
