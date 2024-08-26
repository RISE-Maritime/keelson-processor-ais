import pyais.constants
import pyais.messages
import zenoh
import logging
import warnings
import atexit
import json
import keelson
from terminal_inputs import terminal_inputs
from keelson.payloads.TimestampedBytes_pb2 import TimestampedBytes
from keelson.payloads.Target_pb2 import Target, TargetDescription, DataSource
from keelson.payloads.LocationFix_pb2 import LocationFix
import pyais
import time
from utilitis import set_navigation_status_enum, set_target_type_enum, position_to_common_center_point, filterAIS, rot_fix, publish_message, position_within_boundary
import socket

session = None
args = None
sock = None

# Storing AIS dimensions for each MMSI for position correction
AIS_DB = {
}


def sub_sjv_data(data):

    received_at, enclosed_at, content = keelson.uncover(data.payload)
    # logging.debug(f"Received at: {received_at} | Enclosed at: {enclosed_at} type {type(enclosed_at)}" )

    # logging.debug(f"Received on: {data.key_expr}")
    time_value = TimestampedBytes.FromString(content)
    # logging.debug(f"Received data: {time_value}")

    # Parse the NMEA0183 AIS data
    nmea_sentence = time_value.value.decode("utf-8")


    if "udp_sjv" in args.publish:
        # Define the UDP server address and port
        server_address = ('127.0.0.1', 1830)
        # Convert the nmea_sentence to bytes
        nmea_sentence_bytes = nmea_sentence.encode('utf-8')
        # Send the nmea_sentence to the UDP server
        logging.debug(f"Sending NMEA sentence SENT")
        sock.sendto(nmea_sentence_bytes, server_address)
        # Close the socket
       # sock.close()
       

    if nmea_sentence.split(",")[0] not in ["!AIVDM", "$ABVSI"]:
        # logging.debug(f"Received NMEA sentence: {nmea_sentence}")

        try:
            decoded = pyais.decode(nmea_sentence)

            if filterAIS(decoded):
                payload_target = Target()
                payload_target.data_source.source.append(
                    DataSource.Source.AIS_PROVIDER)
                payload_target.timestamp.FromNanoseconds(enclosed_at)
                payload_target_description = TargetDescription()
                payload_target_description.data_source.source.append(
                    DataSource.Source.AIS_PROVIDER)
                payload_target_description.timestamp.FromNanoseconds(
                    enclosed_at)

                # MMSI
                payload_target.mmsi = decoded.mmsi
                payload_target_description.mmsi = decoded.mmsi

                # TYPE 1,2 & 3: Position Report Class A
                # TYPE 27: Long Range AIS Broadcast message
                if decoded.msg_type in [1, 2, 3, 27]:

                    # NAVIGATIONN STATUS
                    status = decoded.status.value
                    payload_target.navigation_status = set_navigation_status_enum(
                        status)
                    # logging.debug(f"Payload_target_description: {TargetDescription.NavigationStatus.Name(payload_target_description.navigation_status)}")

                    # ROT
                    rot = pyais.messages.from_turn(decoded.turn)
                    rot = rot_fix(rot)
                    payload_target.rate_of_turn_degrees_per_minute = rot

                    # SOG, COG, HDG
                    payload_target.speed_over_ground_knots = decoded.speed
                    payload_target.course_over_ground_knots = decoded.course
                    payload_target.heading_degrees = decoded.heading
                    payload_target.latitude_degrees = decoded.lat
                    payload_target.longitude_degrees = decoded.lon

                    # Correcting AIS position if vessel outline is available
                    if str(decoded.mmsi) in AIS_DB.keys():
                        if "to_stern" in AIS_DB[str(decoded.mmsi)].keys():
                            latitude_adj, longitude_adj = position_to_common_center_point(decoded.lat, decoded.lon, decoded.heading, AIS_DB[str(
                                decoded.mmsi)]["to_bow"], AIS_DB[str(decoded.mmsi)]["to_stern"], AIS_DB[str(decoded.mmsi)]["to_port"], AIS_DB[str(decoded.mmsi)]["to_starboard"])
                            payload_target.latitude_degrees = latitude_adj
                            payload_target.longitude_degrees = longitude_adj
                                     

                    # Managing AIS within area of interest
                    if position_within_boundary(payload_target.latitude_degrees, payload_target.longitude_degrees, args):
                        # for AIS position correction
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "position_within_boundary": True
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "position_within_boundary": True
                            }
                        publish_message(payload_target, "target",
                                        decoded.mmsi, session, args, logging)
                    else:
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "position_within_boundary": False
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "position_within_boundary": False
                            }

                # TYPE 18: Standard Class B CS Position Report
                elif decoded.msg_type in [18]:

                    payload_target.speed_over_ground_knots = decoded.speed
                    payload_target.longitude_degrees = decoded.lon
                    payload_target.latitude_degrees = decoded.lat
                    payload_target.course_over_ground_knots = decoded.course
                    payload_target.heading_degrees = decoded.heading

                    # Managing AIS within area of interest
                    if position_within_boundary(payload_target.latitude_degrees, payload_target.longitude_degrees, args):
                        # for AIS position correction
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "position_within_boundary": True
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "position_within_boundary": True
                            }
                        publish_message(
                            payload_target, "target", decoded.mmsi, session, args, logging)
                    else:
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "position_within_boundary": False
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "position_within_boundary": False
                            }

                elif decoded.msg_type in [24]:  # TYPE 24: Static Data Report
                    json_decoded = decoded.to_json()
                    # logging.debug(f"Decoded AIS message: {decoded}")

                    if "shipname" in json_decoded:  # Part A
                        payload_target_description.name = decoded.shipname
                        
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "shipname": decoded.shipname
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "shipname": decoded.shipname
                            }

                    else:  # Part B
                        payload_target_description.callsign = decoded.callsign
                        payload_target_description.vessel_type = set_target_type_enum(
                            decoded.ship_type)

                        width = decoded.to_port + decoded.to_starboard
                        length = decoded.to_bow + decoded.to_stern

                        new_to_bow = length / 2
                        new_to_stern = -length / 2
                        new_to_starboard = width / 2
                        new_to_port = -width / 2

                        payload_target_description.to_bow_meters = new_to_bow
                        payload_target_description.to_stern_meters = new_to_stern
                        payload_target_description.to_starboard_meters = new_to_starboard
                        payload_target_description.to_port_meters = new_to_port

                        # for AIS position correction
                        if str(decoded.mmsi) in AIS_DB:
                            AIS_DB[str(decoded.mmsi)] = {
                                **AIS_DB[str(decoded.mmsi)],
                                "to_bow": decoded.to_bow,
                                "to_stern": decoded.to_stern,
                                "to_starboard": decoded.to_starboard,
                                "to_port": decoded.to_port,
                            }
                        else:
                            AIS_DB[str(decoded.mmsi)] = {
                                "to_bow": decoded.to_bow,
                                "to_stern": decoded.to_stern,
                                "to_starboard": decoded.to_starboard,
                                "to_port": decoded.to_port,
                                "position_within_boundary": False
                            }


                    # Managing AIS within area of interest
                    if str(decoded.mmsi) in  AIS_DB.keys():
                        if "shipname" in AIS_DB[str(decoded.mmsi)].keys():
                            payload_target_description.name = AIS_DB[str(decoded.mmsi)]["shipname"]

                        if "position_within_boundary" in AIS_DB[str(decoded.mmsi)].keys():
                            if AIS_DB[str(decoded.mmsi)]["position_within_boundary"]:
                                publish_message(payload_target_description, "target_description",
                                                decoded.mmsi, session, args, logging)
                                    

                # else:
                #     logging.debug(f"Decoded AIS message: {decoded}")

        except Exception as e:
            logging.warning(f"Error parsing AIS: {e}")


def sub_digitraffic_data(data):
    logging.debug(f"Received on: {data.key_expr}")

    # logging.debug(f"Received data: {data.payload}") # Receiving plain json
    json_string = data.payload.decode('utf-8')

    # Convert the JSON string to a dictionary
    data_dict = json.loads(json_string)

    time_now = time.time_ns()
    payload_target = Target()
    payload_target.data_source.source.append(DataSource.Source.AIS_PROVIDER)
    payload_target.timestamp.FromNanoseconds(time_now)
    payload_target_description = TargetDescription()
    payload_target_description.data_source.source.append(
        DataSource.Source.AIS_PROVIDER)
    payload_target_description.timestamp.FromNanoseconds(time_now)

    if str(data.key_expr).split("/")[-1] == "location":

        # logging.debug(f"Location: {data_dict}")

        mmsi = str(data.key_expr).split("/")[-2]
        payload_target.mmsi = int(mmsi)

        # NAVIGATIONN STATUS
        status = data_dict["navStat"]
        payload_target.navigation_status = set_navigation_status_enum(status)

        # ROT, SOG, COG, HDG
        payload_target.rate_of_turn_degrees_per_minute = data_dict["rot"]
        payload_target.speed_over_ground_knots = data_dict["sog"]
        payload_target.course_over_ground_knots = data_dict["cog"]
        payload_target.heading_degrees = data_dict["heading"]

        # Correcting AIS position if vessel outline is available
        if str(mmsi) in AIS_DB:
            if "to_stern" in AIS_DB[str(mmsi)].keys():
                logging.debug(f"Adjusting position for MMSI: {mmsi}")
                latitude_adj, longitude_adj = position_to_common_center_point(data_dict["lat"], data_dict["lon"], data_dict["heading"], AIS_DB[str(
                    mmsi)]["to_bow"], AIS_DB[str(mmsi)]["to_stern"], AIS_DB[str(mmsi)]["to_port"], AIS_DB[str(mmsi)]["to_starboard"])
                payload_target.latitude_degrees = latitude_adj
                payload_target.longitude_degrees = longitude_adj

                payload_target.position.latitude = latitude_adj
                payload_target.position.longitude = longitude_adj

        else:
            payload_target.latitude_degrees = data_dict["lat"]
            payload_target.longitude_degrees = data_dict["lon"]

        # Managing AIS within area of interest
        if position_within_boundary(payload_target.latitude_degrees, payload_target.longitude_degrees, args):
            # for AIS position correction

            if str(mmsi) in AIS_DB:
                AIS_DB[str(mmsi)] = {
                    **AIS_DB[str(mmsi)],
                    "position_within_boundary": True
                }
            else:
                AIS_DB[str(mmsi)] = {
                    "position_within_boundary": True
                }
            publish_message(
                payload_target, "target", mmsi, session, args, logging)
        else:
            if str(mmsi) in AIS_DB:
                AIS_DB[str(mmsi)] = {
                    **AIS_DB[str(mmsi)],
                    "position_within_boundary": False
                }
            else:
                AIS_DB[str(mmsi)] = {
                    "position_within_boundary": False
                }

    elif str(data.key_expr).split("/")[-1] == "metadata":
        logging.debug(f"Metadata: {data_dict}")

        # MMSI
        mmsi = str(data.key_expr).split("/")[-2]
        payload_target.mmsi = int(mmsi)
        payload_target_description.mmsi = int(mmsi)

        payload_target_description.name = data_dict["name"]
        payload_target_description.callsign = data_dict["callSign"]
        payload_target_description.vessel_type = set_target_type_enum(
            data_dict["type"])
        payload_target_description.imo = data_dict["imo"]

        width = data_dict["refC"] + data_dict["refD"]
        length = data_dict["refB"] + data_dict["refA"]

        new_to_bow = length / 2
        new_to_stern = -length / 2
        new_to_starboard = width / 2
        new_to_port = -width / 2

        payload_target_description.to_bow_meters = new_to_bow
        payload_target_description.to_stern_meters = new_to_stern
        payload_target_description.to_starboard_meters = new_to_starboard
        payload_target_description.to_port_meters = new_to_port

        payload_target_description.destination = data_dict["destination"]
        payload_target_description.draft_meters = data_dict["draught"]
        payload_target_description.estimated_time_of_arrival = str(
            data_dict["eta"])

        # for AIS position correction
        if str(mmsi) in AIS_DB:
            AIS_DB[str(mmsi)] = {
                **AIS_DB[str(mmsi)],
                "to_bow": data_dict["refA"],
                "to_stern": data_dict["refB"],
                "to_starboard": data_dict["refD"],
                "to_port": data_dict["refC"]
            }
        else:
            AIS_DB[str(mmsi)] = {
                "to_bow": data_dict["refA"],
                "to_stern": data_dict["refB"],
                "to_starboard": data_dict["refD"],
                "to_port": data_dict["refC"],
                "position_within_boundary": False
            }

        # Managing AIS within area of interest
        if AIS_DB[str(mmsi)]["position_within_boundary"]:
            publish_message(payload_target_description, "target_description",
                            mmsi, session, args, logging)

    else:
        logging.warning(f"Unknown data: {data_dict}")


if __name__ == "__main__":

    # Input arguments and configurations
    args = terminal_inputs()
    # Setup logger
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=args.log_level
    )
    logging.captureWarnings(True)
    warnings.filterwarnings("once")

    # Construct session
    logging.info("Opening Zenoh session...")
    conf = zenoh.Config()

    if args.connect is not None:
        conf.insert_json5(zenoh.config.CONNECT_KEY, json.dumps(args.connect))
    session = zenoh.open(conf)

    def _on_exit():
        session.close()

    atexit.register(_on_exit)
    logging.info(f"Zenoh session established: {session.info()}")

    # UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    #################################################
    # Setting up SUBSCRIBERs

    # Sjöfartsverket AIS subscriber
    if "sjofartsverket" in args.subscribe:
        key_exp_pub_sjv = keelson.construct_pub_sub_key(
            realm=args.realm,
            entity_id="sjofartsverket",
            subject="raw/ais/nmea0183",  # Needs to be a supported subject
            source_id="**",
        )
        sub_sjv = session.declare_subscriber(
            key_exp_pub_sjv,
            sub_sjv_data,
        )
        logging.debug(f"Subscribing to: {key_exp_pub_sjv}")

    # Digitraffic subscriber
    if "digitraffic" in args.subscribe:
        key_exp_pub_digitraffic = keelson.construct_pub_sub_key(
            realm=args.realm,
            entity_id="digitraffic",
            subject="raw/ais/json/vessels-v2",  # Needs to be a supported subject
            source_id="**",
        )
        sub_digitraffic = session.declare_subscriber(
            key_exp_pub_digitraffic,
            sub_digitraffic_data,
        )
        logging.debug(f"Subscribing to: {key_exp_pub_digitraffic}")
