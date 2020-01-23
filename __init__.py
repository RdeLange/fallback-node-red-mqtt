from mycroft.skills.core import FallbackSkill
from os.path import dirname
from mycroft.util.log import getLogger
from mycroft.util.log import LOG
from mycroft.api import DeviceApi
from websocket import create_connection
import time
import uuid
import string
import random
import json
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import re

__author__ = 'RdeLange'

# Logger: used for debug lines, like "LOGGER.debug(xyz)". These
# statements will show up in the command line when running Mycroft.
LOGGER = getLogger(__name__)

# clear any previously connected mqtt clients on first load
try:
    mqttc
    LOG.info('Client exist')
    mqttc.loop_stop()
    mqttc.disconnect()
    LOG.info('Stopped old client loop')
except NameError:
    mqttc = mqtt.Client()
    LOG.info('Client created')


# The logic of each skill is contained within its own class, which inherits
# base methods from the MycroftSkill class with the syntax you can see below:
# "class ____Skill(FallbackSkill)"
class NodeRedMQTTFallback(FallbackSkill):
    """
        A Fallback skill to node red via the mqtt protocol
    """
    def __init__(self):
        super(NodeRedMQTTFallback, self).__init__(name='Node Red MQTT Fallback')
        # Initialize settings values
        self._is_setup = False
        self.notifier_bool = True
        self.deviceUUID = ''  # This is the unique ID based on the Mac of this unit
        self.targetDevice = ''  # This is the targed device_id obtained through mycroft dialog
        self.base_topic = ''
        self.MQTT_Enabled = ''
        self.broker_address = ''
        self.broker_port = ''
        self.broker_uname = ''
        self.broker_pass = ''
        self.location_id = ''
        self.response_location = ''
        self.fallback_prio = self.settings.get("fallback_prio",50)



    def initialize(self):
        """
            Registers the fallback skill
        """
        self.register_fallback(self.handle_fallback, self.fallback_prio)
        self.load_data_files(dirname(__file__))
        #  Check and then monitor for credential changes
        self.settings.set_changed_callback(self.on_websettings_changed)
        self.on_websettings_changed()
        self.deviceUUID = self.get_mac_address()
        mqttc.on_connect = self.on_connect
        mqttc.on_message = self.on_message
        mqttc.on_disconnect = self.on_disconnect
        if self._is_setup:
            self.mqtt_init()

    def handle_fallback(self, message):
        """
            Get the utterance and send it to Nodered via  MQTT
        """
        self.success = False
        message_json = {}  # create json object
        message_json['source'] = str(self.location_id)
        voice_payload = str(message.data.get('utterance'))
        self.targetDevice = "noderedfallbackserver"
        message_json["command"] = voice_payload
        LOG.info("NodeRedMQTTFallback preparing to Send a message to " + self.targetDevice)
        mqtt_path = self.base_topic + "/NodeRedFallback/" + str(self.targetDevice).lower()
        self.send_MQTT(mqtt_path, message_json)
        self.wait_for_node()
        if self.waiting_for_node == True:
            LOG.info("NodeRedMQTTFallback time out while processing intent")
            if self.success == True:
                self.waiting_for_node = False
            elif self.success == False:
                self.waiting_for_node = False
        elif self.waiting_for_node == False:
            if self.success == True:
                LOG.info("NodeRedMQTTFallback feedback from server and answer could be processed")
                self.waiting_for_node = False
            elif self.success == False:
                LOG.info("NodeRedMQTTFallback feedback from server but answer could not be processed")
                self.waiting_for_node = False

        return self.success


    def on_connect(self, mqttc, obj, flags, rc):
        LOG.info("NodeRedMQTTFallback Connection Verified")
        LOG.info("This device location is: " + DeviceApi().get()["description"])
        mqtt_path = self.base_topic + "/NodeRedFallback/" + str(self.location_id)
        qos = 0
        mqttc.subscribe(mqtt_path, qos)
        LOG.info('NodeRedMQTTFallback-Skill Subscribing to: ' + mqtt_path)

    def on_disconnect(self, mqttc, obj, flags, rc):
        self._is_setup = False
        LOG.info("NodeRedMQTTFallback has Dis-Connected")

    def on_message(self, mqttc, obj, msg):  # called when a new MQTT message is received
        # Sample Payload {"source":"basement", "message":"is dinner ready yet"}
        LOG.info('NodeRedMQTTFallback message received for location id: ' + str(self.location_id))
        LOG.info("This device location is: " + DeviceApi().get()["description"])
        self.waiting_for_node = False
        try:
            mqtt_message = msg.payload.decode('utf-8')
            LOG.info(msg.topic + " " + str(msg.qos) + ", " + mqtt_message)
            new_message = json.loads(mqtt_message)
            if "command" in new_message:
                # example: {"source":"kitchen", "command":"what time is it"}
                LOG.info('NodeRedMQTTFallback Command Received! - ' + new_message["command"] + ', From: ' + new_message["source"])
                self.response_location = new_message["source"]
                self.send_message(new_message["command"])
                self.success = True
            elif "message" in new_message:
                # example: {"source":"kitchen", "message":"is dinner ready yet"}
                self.response_location = ''
                LOG.info('NodeRedMQTTFallbackMessage Received! - ' + new_message["message"] + ', From: ' + new_message["source"])
                self.speak_dialog('message', data={"result": new_message["message"]}, expect_response=False)
                self.success = True
            else:
                LOG.info('NodeRedMQTTFallback Unable to decode the MQTT Message')
                self.success = False
        except Exception as e:
            LOG.error('Error: {0}'.format(e))
            self.success = False

    def clean_base_topic(self, basetopic):
        if basetopic[-1] == "/":
            basetopic = basetopic[0:-1]
        if basetopic[0] == "/":
            basetopic = basetopic[1:]
        return basetopic

    def on_websettings_changed(self):  # called when updating mycroft home page
        self._is_setup = False
        self.MQTT_Enabled = self.settings.get("MQTT_Enabled", False)  # used to enable / disable mqtt
        self.broker_address = self.settings.get("broker_address", "127.0.0.1")
        raw_base_topic = self.settings.get("base_topic", "Mycroft")
        self.base_topic = self.clean_base_topic(raw_base_topic)
        self.broker_port = self.settings.get("broker_port", 1883)
        self.broker_uname = self.settings.get("broker_uname", "")
        self.broker_pass = self.settings.get("broker_pass", "")
        self.fallback_prio = self.settings.get("fallback_prio",50)
        self.timeout = self.settings.get("fallback_timeout",15)
        this_location_id = str(DeviceApi().get()["description"])
        self.location_id = this_location_id.lower()
        LOG.info("This device location is: " + str(self.location_id))
        try:
            mqttc
            LOG.info('Client exist')
            mqttc.loop_stop()
            mqttc.disconnect()
            LOG.info('Stopped old client loop')
        except NameError:
            mqttc = mqtt.Client()
            LOG.info('Client re-created')
        LOG.info("Websettings Changed! " + self.broker_address + ", " + str(self.broker_port))
        self.mqtt_init()
        self._is_setup = True

    def mqtt_init(self):  # initializes the MQTT configuration and subscribes to its own topic
        if self.MQTT_Enabled:
            LOG.info('NodeRedMQTTFallback MQTT Is Enabled')
            try:
                LOG.info("Connecting to host: " + self.broker_address + ", on port: " + str(self.broker_port))
                if self.broker_uname and self.broker_pass:
                    LOG.info("Using MQTT Authentication")
                    mqttc.username_pw_set(username=self.broker_uname, password=self.broker_pass)
                mqttc.connect_async(self.broker_address, self.broker_port, 60)
                mqttc.loop_start()
                LOG.info("NodeRedMQTTFallback MQTT Loop Started Successfully")
            except Exception as e:
                LOG.error('Error: {0}'.format(e))

    def id_generator(self, size=6, chars=string.ascii_uppercase + string.digits):
        return ''.join(random.choice(chars) for _ in range(size))

    def get_mac_address(self):  # used to create a unique UUID for this device that
        node = uuid.getnode()
        mac = uuid.UUID(int=node).hex[-12:]
        LOG.info("MQTT using UUID: " + mac)
        return mac

    def send_MQTT(self, my_topic, my_message):  # Sends MQTT Message
        if self.MQTT_Enabled and self._is_setup:
            LOG.info("NodeRedFallback MQTT: " + my_topic + ", " + json.dumps(my_message))
            LOG.info("address: " + self.broker_address + ", Port: " + str(self.broker_port))
            publish.single(my_topic, json.dumps(my_message), hostname=self.broker_address)
        else:
            LOG.info("MQTT for NodeRedMQTTFallback has been disabled in the websettings at https://home.mycroft.ai")

    def send_message(self, message):  # Sends the remote received commands to the messagebus
        LOG.info("NodeRedMQTTFallback Sending a command to the message bus: " + message)
        payload = json.dumps({
            "type": "recognizer_loop:utterance",
            "context": "",
            "data": {
                "utterances": [message]
            }
        })
        uri = 'ws://localhost:8181/core'
        ws = create_connection(uri)
        ws.send(payload)
        ws.close()

    def wait_for_node(self):
        start = time.time()
        self.waiting_for_node = True
        while self.waiting_for_node and time.time() - start < float(self.timeout):
            time.sleep(0.3)

    def shutdown(self):
        """
            Remove this skill from list of fallback skills.
        """
        self.remove_fallback(self.handle_fallback)
        super(NodeRedMQTTFallback, self).shutdown()


def create_skill():
    return NodeRedMQTTFallback()
