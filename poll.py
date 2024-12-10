from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from w1thermsensor import W1ThermSensor
import configparser
import argparse
import socket
import json
import dateutil
import traceback


# gpsd commands
MSG_WATCH_ENABLE = '?WATCH={"enable":true}'
MSG_WATCH_DISABLE = '?WATCH={"enable":false}'
MSG_POLL = '?POLL;'


class StatusPoller():
    """Polls selected sensors and collects data from gpsd to influxdb"""


    def __init__(self, ini_file):
        self.config = configparser.ConfigParser()
        self.config.read(ini_file)

        # make connection to influxdb
        write_api = self.influxdb_connection()

        try:
            # collect data from different endpoints
            p = Point("status")
            self.collect_systemdata(p)  # cpu temp from /sys
            self.collect_sensordata(p)  # read selected onewire temperature sensors
            
            gpsd_host = self.config['GPSD']["Host"]
            gpsd_port = int(self.config['GPSD']["Port"])    
            influx_bucket = self.config['INFLUXDB']['Bucket']

            polled = self.poll_gpsd(gpsd_host, gpsd_port)   # get data from from gpsd
            parsed = self.parse_poll(polled)                # parse data from gpsd
            self.collect_gpsddata(parsed, p)                # add gpsd data to same influxdb point 
            self.collect_satellitedata(parsed, influx_bucket, write_api)    # add satellite data separately to influxdb
        except Exception as e:
            traceback.print_exc()
        finally:
            write_api.write(bucket=influx_bucket, record=p)

        write_api.close()


    def influxdb_connection(self):
        """ Open connection to influxDB server and return write_api """
        influx_host = self.config['INFLUXDB']['Host']
        influx_token = self.config['INFLUXDB']['Token']
        influx_org = self.config['INFLUXDB']['Org']

        client = InfluxDBClient(url=influx_host, token=influx_token, org=influx_org)
        
        return client.write_api(write_options=SYNCHRONOUS)


    def collect_systemdata(self, p):
        """ Collect data about system we run on """

        # only CPU temp for now
        cput = self.check_CPU_temp()
        p.field("cpu_temp", round(cput, 2))


    def check_CPU_temp(self):
        """Get the CPU temperature"""
        temp = None
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as infile:
            temp = float(infile.read()) / 1000
        return temp


    def collect_sensordata(self, p):
        w1_sensors = {}

        # the ini file has sensorids prefixed with id_, we strip that
        # off and add them to a dict with name we want to use in influxdb
        for sensorid in self.config["ONEWIRE"]:
            realid = sensorid[3:]
            w1_sensors[realid] = self.config["ONEWIRE"][sensorid]

        for sensor in W1ThermSensor.get_available_sensors():
            if sensor.id in w1_sensors:
                #print("Sensor %s has temperature %.2f" % (sensor.id, sensor.get_temperature()))    
                p.field(f"{w1_sensors[sensor.id]}_temp", round(sensor.get_temperature(), 2))


    def poll_gpsd(self, host, port):
        """ Poll the GPSD server via socket connection."""
        polled = {}
        gpsd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            gpsd.connect((host, port))
            gpsd.settimeout(1)
            data = gpsd.recv(1024)

            gpsd.sendall(MSG_WATCH_ENABLE.encode())
            data = gpsd.recv(1024)

            gpsd.sendall(MSG_POLL.encode())
            try:
                data = b""
                while True:
                    buff = gpsd.recv(1024)
                    if not buff:
                        break
                    data += buff
            except Exception as e:
                pass

            polled = json.loads(data.decode())
            
            gpsd.sendall(MSG_WATCH_DISABLE.encode())
            data = gpsd.recv(1024)
        except Exception as e:
            traceback.print_exc()
        finally:
            gpsd.close()

        return polled


    def print_dict(self, d, indent=0):
        for key, value in d.items():
            if isinstance(value, dict):
                print(f"{indent * '  '} {key}:")
                self.print_dict(value, indent + 2)
            else:
                print(f"{indent * '  '} {key}: {value}")

    def parse_poll(self, polled):
        """ Parse gpsd reponse into something more manageable """
        parsed = {}
        parsed["satellites"] = []
        parsed["sat_count_used"] = 0
        parsed["sat_count_ignored"] = 0
        parsed["sat_count_total"] = 0

        #self.print_dict(polled)

        if not polled["class"] == "POLL":
            raise Exception("Wrong type of response")

        if polled.get("tpv") is not None:
            # 0=mode not set, 1=no fix, 2=2D fix, 3=3D fix
            mode = polled["tpv"][0]["mode"]
            parsed["mode"] = mode
            parsed["time"] = polled["time"]
            if mode >= 2:
                parsed["lat"] = polled["tpv"][0]["lat"]     # latitude
                parsed["lon"] = polled["tpv"][0]["lon"]     # longitude
                parsed["epx"] = polled["tpv"][0]["epx"]     # longitude error estimate in meters
                parsed["epy"] = polled["tpv"][0]["epy"]     # latitude error estimate in meters
            if mode >= 3:
                parsed["alt"] = polled["tpv"][0]["altHAE"]  # altitude, height above ellipsoid, in meters 
                parsed["epv"] = polled["tpv"][0]["epv"]     # estimated vertical error in meters

        if polled.get("sky") is not None:
            for sat in polled["sky"][0]["satellites"]:
                if sat["used"] == True:
                    # add constellation acronym to data
                    match sat["gnssid"]:
                        case 0: sat["constellation"] = "GP"     # GPS
                        case 1: sat["constellation"] = "SB"     # SBAS
                        case 2: sat["constellation"] = "GA"     # Galileo
                        case 3: sat["constellation"] = "BD"     # BeiDou
                        case 4: sat["constellation"] = "IM"     # IMES
                        case 5: sat["constellation"] = "QZ"     # QZSS
                        case 6: sat["constellation"] = "GL"     # GLONAS
                        case 7: sat["constellation"] = "IR"     # NavIC

                    parsed["satellites"].append(sat)
                    parsed["sat_count_used"] += 1
                else:
                    parsed["sat_count_ignored"] += 1

                parsed["sat_count_total"] +=1

        return parsed


    def collect_gpsddata(self, parsed, p):
        """ Put parsed gpsd data into datapoint """
        
        mode = parsed["mode"];
        p.field("mode", mode)

        if mode >= 2:
            # add data available on 2d fix
            p.field("lat", parsed["lat"])
            p.field("lon", parsed["lon"])
            p.field("satellites", parsed["sat_count_total"])
            p.field("sats_used", parsed["sat_count_used"])
            p.field("sats_ignored", parsed["sat_count_ignored"])
            p.field("error_lon", parsed["epx"])
            p.field("error_lat", parsed["epy"])
        if mode >= 3:
            # add data available on 3d fix
            p.field("alt", parsed["alt"])
            p.field("error_vertical", parsed["epv"])


    def collect_satellitedata(self, parsed, bucket, write_api):
        """ Add satellinte data to datapoint and write to influxdb """ 

        # same timestamp for all
        ts = int(dateutil.parser.parse(parsed["time"]).timestamp()) * 1000000000
            
        for sat in parsed["satellites"]:
            # add datapoint for each visible satellite
            p2 = Point("satellite")
            p2.tag("sat", f'{sat["constellation"]}{sat["svid"]}')
            p2.tag("gnssid", sat["gnssid"])
            p2.tag("co", sat["constellation"])
            p2.field("el", sat["el"])
            p2.field("az", sat["az"])
            p2.field("ss", sat["ss"])
            p2.field("PRN", sat["PRN"])
            p2.field("svid", sat["svid"])
            p2.time(ts)

            write_api.write(record=p2, bucket=bucket)


if __name__ == "__main__":
    # parse command line arguments
    parser = argparse.ArgumentParser(description='GPSD status poller')
    parser.add_argument('ini_file', type=str, help='Path to the INI file')
    args = parser.parse_args()
    
    StatusPoller(args.ini_file)
