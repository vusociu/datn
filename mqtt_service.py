import paho.mqtt.client as mqtt
import time
import socket, uuid


class MQTTService:
    def __init__(
        self,
        broker="192.168.5.51",
        port=1883,
        username="vund",
        password="131003",
        client_id = f"FaceRec-{socket.gethostname()}-{uuid.uuid4().hex[:6]}",
    ):
        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.topic_handlers = {}

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            protocol=mqtt.MQTTv311
        )

        self.client.username_pw_set(username, password)

        # Callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message


        # Auto reconnect (RẤT QUAN TRỌNG)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.max_inflight_messages_set(10)
        self.client.max_queued_messages_set(50)

        # Last will
        self.client.will_set("status/client", "offline", qos=1, retain=False)

    # ================= CALLBACKS =================

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("MQTT connected")
            client.publish("status/client", "online", qos=1, retain=False)

            # Resubscribe
            for topic in self.topic_handlers:
                client.subscribe(topic, qos=1)
                print(f"Resubscribed: {topic}")
        else:
            print(f"MQTT connect failed rc={rc}")

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print("MQTT disconnected unexpectedly – auto reconnecting")
        else:
            print("MQTT disconnected normally")

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        print(f"{msg.topic}: {payload}")

        handler = self.topic_handlers.get(msg.topic)
        if handler:
            handler(payload)

    # ================= PUBLIC API =================

    def connect(self):
        print(f"Connecting to MQTT {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port, keepalive=120)
        self.client.loop_start()

    def disconnect(self):
        self.client.publish("status/client", "offline", qos=1, retain=False)
        time.sleep(0.2)
        self.client.disconnect()
        self.client.loop_stop()

    def subscribe(self, topic, handler):
        self.topic_handlers[topic] = handler
        if self.client.is_connected():
            self.client.subscribe(topic, qos=1)
            print(f"Subscribed: {topic}")

    def publish(self, topic, message, qos=0):
        if not self.client.is_connected():
            return False
        self.client.publish(topic, message, qos=qos)
        return True

    def is_connected(self):
        return self.client.is_connected()
