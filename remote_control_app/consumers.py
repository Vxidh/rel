# remote_control_app/consumers.py

from channels.generic.websocket import AsyncWebsocketConsumer
import json
import logging
import base64

# These are in-memory dictionaries shared between consumers
from relay_server.consumers import nodes_available, node_connections

logger = logging.getLogger(__name__)

class RemoteControlConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.node_id = self.scope['url_route']['kwargs']['node_id']
        
        if self.node_id not in nodes_available:
            logger.warning(f"[RemoteControl] Connection rejected: Node {self.node_id} is not connected.")
            await self.close(code=4004)
            return

        await self.accept()
        node_connections[self.node_id] = self
        logger.info(f"[RemoteControl] Controller for node {self.node_id} connected.")

    async def disconnect(self, close_code):
        if node_connections.get(self.node_id) == self:
            node_connections.pop(self.node_id, None)
        logger.info(f"[RemoteControl] Controller for node {self.node_id} disconnected.")

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            try:
                data = json.loads(text_data)
                command_type = data.get("commandType")
                request_id = data.get("requestId", "unknown")
                node_consumer = nodes_available.get(self.node_id)
                if node_consumer:
                    await node_consumer.send_command_to_node(request_id, data)
                    logger.info(f"Forwarded command '{command_type}' to node {self.node_id}")
                else:
                    logger.warning(f"Node {self.node_id} not available to receive command '{command_type}'")
                    await self.send(text_data=json.dumps({ "type": "error", "message": f"Node {self.node_id} is not connected." }))
            except Exception as e:
                logger.exception(f"Error processing command from controller for node {self.node_id}: {e}")

    async def send_image_frame(self, frame_data_base64):
        """
        Receives a base64 encoded image frame and sends it to the web controller.
        """
        await self.send(text_data=json.dumps({
            'type': 'image_frame',
            'frame_data': frame_data_base64
        }))
