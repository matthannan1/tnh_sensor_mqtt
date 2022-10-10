#!/usr/bin/env python3

"""
Rather than use a crappy DHT22 connected to an ESP3266 for temp and humidity
readings in the basement, I am am going to use the existing, and vastly
superior, SHT31D that has been running reliably for years now and is
connected to the I2C bus on a Raspberry Pi 3B.
It seems that the easiest way to get this data to Home Assistant is via MQTT.
I figured there had to bve a way to get at the data via Grafana, but this
does not appear to be the case. And you can forget about trying to source it
from the original SQLite database.

Step 1: get the readings - Done
Step 2: publish them to the MQTT broker on HA

Issue 1: ran headlong into the CRON jobs, which run at the top and bottom of
the hour and one minute and 31 minutes past. Need to think how to avoid this.
Perhaps 5 min updates and somehow avoid the top of the hour?
while mins != "00" or "30":
something like that?
5 mins is 300 seconds for the time.sleep(300)
>> RESOLVED

Issue 2: need username and password in order to publish to the HA broker.
Logs clearly show it is making contact, but not authenticating.
   username_pw_set(username, password=None)
>> RESOLVED

Issue 3: how to publish both temp and humid at the same time?
>> RESOLVED!!!

MJH 04 Aug 2022
---------------------------------
07 Aug 2022

Like the Dwarves in Moria, I got greedy, dug too deep, and let loose a Balrog.
In other words, I completely messed up my Python while attempting to upgrade
from 3.6.6 to 3.10.whatever.
I had to completely reload the OS...several times.
This got me thinking that leaving the script running, but sitting at time.sleep(300)
was not exactly an efficient use of this Pi3B+'s resources. To solve this, I modified
the CRON job to run every 5 mins, while still dodging the "interesting" times when
the other scripts are using the sensor.
Just confirmed that this is working. It sent an MQTT publish at 9:02, and another,
on schedule, at 9:05.

I want to syslog the delivery notfication code, but that is a something for another day.
I have enough going on rebuilding this Pi!
---------------------------------------
24 Sep 2022

Removed sensitive info (username, pwd, etc) to secrets.py file in prep for uploading to GitHub,
which is now a PiTA from Linux on ARM what with the new 2F authentication BS.
------------------------------------------
08 Oct 2022

Adding PMS5003 patriculate matter sensor using the pms5003 library.
sudo crontab -e
@reboot /usr/bin/python3 /home/pi/tnh-sensor-mqtt/tnh_sensor_mqtt.py >> ~/cron.log 2>&1

"""

import secrets
import time
import json
from datetime import datetime
import syslog
import adafruit_sht31d
from pms5003 import PMS5003
import board
import busio
import paho.mqtt.client as mqtt


# Sensor stuff
# SHT31d
I2C = busio.I2C(board.SCL, board.SDA)
SENSOR = adafruit_sht31d.SHT31D(I2C)
# PMS5003
pms5003 = PMS5003(
    device='/dev/ttyAMA0',
    baudrate=9600,
    pin_enable=22,
    pin_reset=27
)

# MQTT stuff
MQTT_BROKER = secrets.broker_ip
MQTT_CLIENT = mqtt.Client()
MQTT_CLIENT.username_pw_set(username=secrets.username, password=secrets.password)
MQTT_CLIENT.connect(MQTT_BROKER)
MQTT_CLIENT.loop_start()

# Let the PMS5003 settle out
pms_data = pms5003.read()
time. sleep(30)

while True:
    # Gather data
    # Get current time and check the minutes
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_minute = current_time[3:5]

    # These are the minutes at which the sensor is busy working
    # for Django and Grafana via CRON jobs
    AVOID_LIST = ["00", "01", "30", "31"]
    if current_minute in AVOID_LIST:
        time.sleep(60)
        continue
    else:
        ## temp is converted to F and rounded to one decimal place
        temp = round((SENSOR.temperature * 1.8 + 32), 1)
        ## humidity reading is rounded to two decimal places
        humid = round(SENSOR.relative_humidity, 2)
        # Read PMS5003
        pms_data = pms5003.read()
        # print(pms_data.pm_per_1l_air(0.3))
        # These need to be set to variables otherwise msgs send zeros
        con_PM1 = pms_data.pm_ug_per_m3(1.0)
        con_PM2dot5 = pms_data.pm_ug_per_m3(2.5)
        con_PM10 = pms_data.pm_ug_per_m3(10)
        decaliter_dot3 = pms_data.pm_per_1l_air(0.3)
        decaliter_dot5 = pms_data.pm_per_1l_air(0.5)
        decaliter_1 = pms_data.pm_per_1l_air(1.0)
        decaliter_2dot5 = pms_data.pm_per_1l_air(2.5)
        decaliter_5 = pms_data.pm_per_1l_air(5)
        decaliter_10 = pms_data.pm_per_1l_air(10)

        # Publish Data
        # Next two lines retained for for history...example of sending one piece of data
        # MQTT_CLIENT.publish("temperature, temp)
        # print("Just published", temp, "to topic BASEMENT_TEMPERATURE")

        # Bundle data into json format
        msgs = json.dumps({"temperature": temp,
                           "humidity": humid,
                           "pm_ug_per_m3_1": con_PM1,
                           "pm_ug_per_m3_2dot5": con_PM2dot5,
                           "pm_ug_per_m3_10": con_PM10,
                           "pm_per_1l_air_dot3": decaliter_dot3,
                           "pm_per_1l_air_dot5": decaliter_dot5,
                           "pm_per_1l_air_1": decaliter_1,
                           "pm_per_1l_air_2dot5": decaliter_2dot5,
                           "pm_per_1l_air_5": decaliter_5,
                           "pm_per_1l_air_10": decaliter_10
                          })

        # print(msgs)

        # Send it! QoS = 0, Pesistence = True
        MQTT_CLIENT.publish("18willow/inside/basement", msgs, 0, True)

        # Tell the world
        syslog.syslog(syslog.LOG_INFO, str(msgs))

        # Gracefully disconnect
        MQTT_CLIENT.disconnect()

        # Sleep 5 mins
        time.sleep(300)
