# File: commands/remote_control.py

import threading
import time
import io
import pyautogui
import logging

log = logging.getLogger(__name__)

class RemoteControlCommands:
    def __init__(self, node_client_ref=None):
        self.node_client_ref = node_client_ref
        self.active_controller = None
        self.streaming = False
        self.stream_thread = None
        self.quality = "medium"

    def start_remote_control(self, params):
        controller_id = params.get('controllerId')
        node_id = params.get('nodeId')
        request_id = params.get('requestId')
        if self.active_controller:
            return {
                'status': 'error',
                'message': f'Node {node_id} is already being controlled by {self.active_controller}',
                'requestId': request_id
            }
        self.active_controller = controller_id
        self.streaming = True
        self.stream_thread = threading.Thread(target=self._stream_images, daemon=True)
        self.stream_thread.start()
        return {
            'status': 'success',
            'message': f'Remote control started for node {node_id} by {controller_id}',
            'requestId': request_id
        }

    def stop_remote_control(self, params):
        controller_id = params.get('controllerId')
        node_id = params.get('nodeId')
        request_id = params.get('requestId')
        if self.active_controller != controller_id:
            return {
                'status': 'error',
                'message': 'You are not the active controller.',
                'requestId': request_id
            }
        self.streaming = False
        self.active_controller = None
        return {
            'status': 'success',
            'message': f'Remote control stopped for node {node_id}',
            'requestId': request_id
        }

    def _stream_images(self):
        # Image streaming now uses a single WebSocket
        # The quality parameter is not used in the Python client, but could be.
        frame_interval = 0.1
        try:
            while self.streaming:
                screenshot = pyautogui.screenshot()
                buf = io.BytesIO()
                screenshot.save(buf, format='JPEG', quality=95)
                img_bytes = buf.getvalue()
                
                if self.node_client_ref and hasattr(self.node_client_ref, 'send_outgoing_ws_message'):
                    message = {
                        "type": "image_stream_frame",
                        "image_bytes": img_bytes,
                        "node_id": self.node_client_ref.node_id
                    }
                    self.node_client_ref.send_outgoing_ws_message(message)
                else:
                    log.warning("NodeClient reference or send method not available. Cannot stream image.")
                    self.streaming = False
                time.sleep(frame_interval)
        except Exception as e:
            log.exception(f"Error during image streaming: {e}")
        finally:
            self.streaming = False

    def send_input(self, params):
        controller_id = params.get('controllerId')
        node_id = params.get('nodeId')
        input_data = params.get('inputData')
        request_id = params.get('requestId')
        if self.active_controller != controller_id:
            return {
                'status': 'error',
                'message': 'You are not the active controller.',
                'requestId': request_id
            }
        # This method is not fully implemented in the provided code, but the structure is correct.
        return {
            'status': 'success',
            'message': f'Input processed for node {node_id}',
            'requestId': request_id
        }