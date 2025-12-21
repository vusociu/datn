#!/usr/bin/env python3
"""
MQTT Connection Test Script
Test MQTT connectivity and reliability features
"""

import time
import signal
import sys
from mqtt_service import MQTTService

# Global flag for graceful shutdown
running = True

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\nShutting down MQTT test...")
    running = False

def test_handler(message):
    """Test message handler"""
    print(f"Test handler received: {message}")

def main():
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)

    print("Starting MQTT Connection Test")
    print("=" * 50)

    # Initialize MQTT Service
    mqtt = MQTTService(
        broker="192.168.1.44",
        port=1883,
        username="admin",
        password="131003",
        client_id="MQTTTestClient"
    )

    # Connect
    print("Connecting to MQTT broker...")
    if not mqtt.connect():
        print("Initial MQTT connection failed")
        return 1

    # Wait for connection
    time.sleep(3)

    # Subscribe to test topic
    print("Subscribing to test topics...")
    mqtt.subscribe_topic("TEST_TOPIC", test_handler)
    mqtt.subscribe_topic("RECOGNITION", lambda msg: print(f"Camera: {msg}"))

    # Test publish
    print("Testing publish functionality...")
    mqtt.publish_message("TEST_TOPIC", "Hello from test script!")
    mqtt.publish_message("RECOGNITION", "test")

    # Monitor connection
    print("Monitoring MQTT connection status...")
    print("Press Ctrl+C to stop")

    test_count = 0
    while running:
        test_count += 1

        # Get status every 10 seconds
        if test_count % 10 == 0:
            status = mqtt.get_connection_status()
            print(f"MQTT Status: Connected={status['connected']}, Topics={len(status['subscribed_topics'])}")

        # Test publish every 30 seconds
        if test_count % 30 == 0:
            mqtt.publish_message("TEST_TOPIC", f"Keepalive #{test_count//30}")

        time.sleep(1)

    # Cleanup
    print("Cleaning up MQTT test...")
    mqtt.disconnect()
    print("MQTT test completed successfully")

    return 0

if __name__ == "__main__":
    sys.exit(main())
