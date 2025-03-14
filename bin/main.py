import zenoh
import pyais.constants
import pyais.messages
import logging
import warnings
import atexit
import json
import keelson
from terminal_inputs import terminal_inputs
from keelson.payloads.Primitives_pb2 import TimestampedBytes
from keelson.payloads.Target_pb2 import Target, TargetDataSource, TargetDescription
from keelson.payloads.GeoJSON_pb2 import GeoJSON
import pyais
import time
from utilitis import set_navigation_status_enum, set_target_type_enum, position_to_common_center_point, filterAIS, rot_fix, publish_message, position_within_boundary
import socket
import pynmea2
import threading
from utilitis import corrBering
import geopy.distance

# Global variables
session = None
args = None
sock = None
latest_os_message = None
last_received_time = None
udp_server_address = None

# Storing AIS dimensions for each MMSI for position correction
AIS_DB = {
}


def main():
    global session, args, sock, udp_server_address
    # Input arguments and configurations
    args = terminal_inputs()
    # Setup logger
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(lineno)d]: %(message)s", level=args.log_level
    )
    
    logging.captureWarnings(True)
    warnings.filterwarnings("once")
    # initiate logging
    zenoh.init_log_from_env_or("error")

        # Define the UDP server address and port
    udp_port = args.udp_port
    udp_host = args.udp_host
    udp_server_address = (udp_host, udp_port)

    if "sjv_nmea_os_udp" in args.publish:
        threading.Thread(target=send_os_nmea, daemon=True).start()

    # Construct session
    logging.info("Opening Zenoh session...")
    conf = zenoh.Config()

    if args.connect is not None:
        conf.insert_json5(zenoh.Config.CONNECT_KEY, json.dumps(args.connect))

    with zenoh.open(conf) as session:
        info = session.info
        logging.info(f"zid: {info.zid()}")
        logging.info(f"routers: {info.routers_zid()}")
        logging.info(f"peers: {info.peers_zid()}")


        def _on_exit():
            session.close()
            if sock:
                sock.close()

        atexit.register(_on_exit)

        # UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        #################################################
        # Setting up SUBSCRIBERs

        # Sjöfartsverket AIS 
        if "sjofartsverket" in args.subscribe:
            key_exp_pub_sjv = keelson.construct_pubsub_key(
                realm=args.realm,
                entity_id="sjofartsverket",
                subject="raw/ais/nmea0183", 
                source_id="**",
            )
            sub_sjv = session.declare_subscriber(
                key_exp_pub_sjv,
                sub_sjv_data,
            )
            logging.debug(f"Subscribing to: {key_exp_pub_sjv}")


        # TODO: UPGRADE - Digitraffic subscriber 
        if "digitraffic" in args.subscribe:
            key_exp_pub_digitraffic = keelson.construct_pubsub_key(
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

        # TODO: CREATE - Kystverket subscriber 
        

        print("Press CTRL-C to quit...")
        while True:
            time.sleep(1)




def send_os_nmea():
    global latest_os_message, last_received_time, sock, udp_server_address
    
    logging.debug(f"Own Ship NMEA UDP thread started!")

    while True:
        if latest_os_message:
           
            current_time = time.time()
           
            if current_time - last_received_time > 1:
                # Perform dead reckoning
                decoded_ais = latest_os_message
                
                time_diff = current_time - last_received_time
                
                predict_minutes = time_diff / 60

                rot = pyais.messages.from_turn(decoded_ais.turn)
           
                # Heading prediction
                heading_change_prediction = decoded_ais.heading + (rot * predict_minutes)
                heading = corrBering(heading_change_prediction)
                logging.debug(f"Heading prediction: {decoded_ais.heading}")

                # Course prediction
                course_change_prediction = decoded_ais.course + (rot * predict_minutes)
                course = corrBering(course_change_prediction)
                logging.debug(f"Course prediction: {decoded_ais.course}")


                # Position prediction
                speed = decoded_ais.speed
                logging.debug(f"Speed: {speed}")
               
                distance_traveled = decoded_ais.speed * (predict_minutes / 60)
                logging.debug(f"predict_minutes: {predict_minutes}")
                logging.debug(f"Distance traveled: {distance_traveled}")
                cog_dir_prediction = decoded_ais.course + (rot * predict_minutes)
                
                pred_positon = list(geopy.distance.distance(nautical=distance_traveled).destination((decoded_ais.lat, decoded_ais.lon), bearing=cog_dir_prediction))
                latitude = pred_positon[0]
                longitude = pred_positon[1]
                logging.debug(f"Position prediction: {longitude}, {longitude}")
            
 
            else:
                decoded_ais = latest_os_message

                # Convert to Own Ship NMEA sentence
                rot = pyais.messages.from_turn(decoded_ais.turn)
                speed = decoded_ais.speed
                course = decoded_ais.course
                heading = decoded_ais.heading
                latitude = decoded_ais.lat
                longitude = decoded_ais.lon

            # Get the current time in UTC
            current_time_str = time.strftime("%H%M%S", time.gmtime())
            current_time_str += ".00"

            # Convert latitude to Degrees Minutes format
            lat_deg = int(latitude)
            lat_min = abs(latitude - lat_deg) * 60
            lat_deg_min = f"{abs(lat_deg):02d}{lat_min:07.4f}"
            # Determine the hemisphere for latitude
            lat_hemisphere = 'N' if latitude >= 0 else 'S'
            # Convert longitude to Degrees Minutes format
            lon_deg = int(longitude)
            lon_min = abs(longitude - lon_deg) * 60
            lon_deg_min = f"{abs(lon_deg):03d}{lon_min:07.4f}"
            # Determine the hemisphere for longitude
            lon_hemisphere = 'E' if longitude >= 0 else 'W'

            # Create the GGA message with the converted latitude and longitude
            msg_position = pynmea2.GGA('GP', 'GGA', (current_time_str, lat_deg_min, lat_hemisphere, lon_deg_min, lon_hemisphere, '1', '09', '0.9', '0.00', 'M', '-32.0', 'M', '', '0000'))
            os_nmea_bytes_pos = msg_position.render().encode('utf-8')
            
            # Create the HDT message with the heading
            msg_heading = pynmea2.HDT('GP', 'HDT', (f"{heading:.1f}", 'T'))
            os_nmea_bytes_hdt = msg_heading.render().encode('utf-8')
            
            # Create the ROT message with the rate of turn
            msg_rot = pynmea2.ROT('GP', 'ROT', (f"{rot:.1f}", 'A'))
            os_nmea_bytes_rot = msg_rot.render().encode('utf-8')

            # Create the VTG message with the course and speed
            msg_vtg = pynmea2.VTG('GP', 'VTG', (f"{course:.1f}", 'T', '', 'M', f"{speed:.1f}", 'N', '', 'K'))
            os_nmea_bytes_vtg = msg_vtg.render().encode('utf-8')

            # Send messages to the UDP server
            sock.sendto(os_nmea_bytes_hdt, udp_server_address)
            sock.sendto(os_nmea_bytes_pos, udp_server_address)
            sock.sendto(os_nmea_bytes_vtg, udp_server_address)
            sock.sendto(os_nmea_bytes_rot, udp_server_address)
            
            logging.debug(f"SJV OS NMEA UDP SENT!")
            time.sleep(1)


def sub_sjv_data(data: zenoh.Sample):
    """
    Processes incoming AIS data, decodes it, and publishes it to specified targets.
    Args:
        data (zenoh.Sample): The incoming data sample containing AIS information.
    Raises:
        Exception: If there is an error sending UDP data or parsing AIS data.
    The function performs the following steps:
    1. Uncovers the payload from the incoming data sample.
    2. Parses the NMEA0183 AIS data from the payload.
    3. Depending on the configuration in `args.publish`, it either:
        a. Sends the NMEA sentence to a UDP server.
        b. Decodes the AIS message and processes it based on its type.
    4. For specific AIS message types, it updates the target information and publishes it if the position is within the area of interest.
    5. Manages AIS data within a boundary and updates the AIS database accordingly.
    """
    
    global args, session, sock, udp_server_address, latest_os_message, last_received_time
    received_at, enclosed_at, content = keelson.uncover(data.payload.to_bytes())
    
    # logging.debug(f"Received at: {received_at} | Enclosed at: {enclosed_at} type {type(enclosed_at)}" )
    # logging.debug(f"Received on: {data.key_expr}")



    # Parse the NMEA0183 AIS data
    time_value = TimestampedBytes.FromString(content)
    nmea_sentence = time_value.value.decode("utf-8")
    # logging.debug(f"Received NMEA sentence: {nmea_sentence}")

    # Forwarding RAW NMEA from SJV to UDP server
    if "sjv_raw_udp" in args.publish:
        try:
            # Convert the nmea_sentence to bytes
            nmea_sentence_bytes = nmea_sentence.encode('utf-8')
            # Send the nmea_sentence to the UDP server
            sock.sendto(nmea_sentence_bytes, udp_server_address)
            logging.debug(f"SJV NMEA UDP SENT!")
        except Exception as e:
            logging.ERROR(f"Error sending UDP data: {e}")

    # Forwarding AIS NMEA from SJV to UDP server and filtering out own ship AIS
    if "sjv_nmea_ais_udp" in args.publish:
        try:
            if nmea_sentence.split(",")[0] not in ["!AIVDM", "$ABVSI"]:
                decoded_ais = pyais.decode(nmea_sentence)
                if decoded_ais.mmsi == args.os_mmsi:
                    logging.debug(f"DO NOT SENDING OS AIS message: {decoded_ais}")
                else:
                    # Convert the nmea_sentence to bytes
                    nmea_sentence_bytes = nmea_sentence.encode('utf-8')
                    # Send the nmea_sentence to the UDP server
                    sock.sendto(nmea_sentence_bytes, udp_server_address)
                    logging.debug(f"SJV NMEA UDP SENT!")
        except Exception as e:
            logging.WARNING(f"Error sending UDP data: {e}")

    # Forwarding OWN SHIP based on SJV AIS NMEA from UDP server
    if ("sjv_nmea_os_udp" in args.publish) and (args.os_mmsi):
        try:
            if nmea_sentence.split(",")[0] not in ["!AIVDM", "$ABVSI"]:
                decoded_ais = pyais.decode(nmea_sentence)
                
                if decoded_ais.mmsi == args.os_mmsi:
                    latest_os_message = decoded_ais
                    last_received_time = time.time()
                    logging.debug(f"Decoded OS AIS message: {decoded_ais}")
            
        except Exception as e:  
            logging.warning(f"Error parsing own ship AIS: {e}")
       
    # Forwarding Keelson Target from SJV to UDP server
    if "sjv_targets" in args.publish:
        if nmea_sentence.split(",")[0] not in ["!AIVDM", "$ABVSI"]:
            # logging.debug(f"Received NMEA sentence: {nmea_sentence}")

            # try:
            decoded = pyais.decode(nmea_sentence)
            logging.debug(f"Decoded AIS message: {decoded}")

            if filterAIS(decoded):
                
                payload_target = Target()
                payload_target.data_source.sources_type.append( TargetDataSource.Source.AIS_PROVIDER)
                payload_target.data_source.source_name = "Sjöfartsverket"
                payload_target.timestamp.FromNanoseconds(enclosed_at)
                payload_target.description.target_type = TargetDescription.TargetType.VESSEL
                payload_target.description.vessel.information.mmsi = decoded.mmsi
                                

                # TYPE 1,2 & 3: Position Report Class A
                # TYPE 27: Long Range AIS Broadcast message
                if decoded.msg_type in [1, 2, 3, 27]:

                    # NAVIGATIONN STATUS
                    status = decoded.status.value
                    payload_target.navigation_status.status = set_navigation_status_enum(status)
                                  
                    # ROT
                    rot = pyais.messages.from_turn(decoded.turn)
                    rot = rot_fix(rot)
                    payload_target.rate_of_turn.rate_of_turn_degrees_per_minute = float(rot)

                    # SOG, COG, HDG
                    payload_target.trajectory_over_ground.speed_over_ground_knots = decoded.speed
                    payload_target.trajectory_over_ground.course_over_ground_degrees = decoded.course
                    payload_target.heading.heading_degrees = decoded.heading
                    payload_target.position.latitude_degrees = decoded.lat
                    payload_target.position.longitude_degrees = decoded.lon        
                       
                    # TODO: UPGRADE - or add transformation to ship outline
                    geojson = GeoJSON()
                    geojson.geojson = json.dumps({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [decoded.lon, decoded.lat]
                        },
                        "properties": {
                            "mmsi": decoded.mmsi,
                            "status": status,
                            "rot": rot,
                            "sog": decoded.speed,
                            "cog": decoded.course,
                            "hdg": decoded.heading
                        }
                    })

                    # Correcting AIS position if vessel outline is available
                    if str(decoded.mmsi) in AIS_DB.keys():
                        if "to_stern" in AIS_DB[str(decoded.mmsi)].keys():
                            latitude_adj, longitude_adj = position_to_common_center_point(decoded.lat, decoded.lon, decoded.heading, AIS_DB[str(
                                decoded.mmsi)]["to_bow"], AIS_DB[str(decoded.mmsi)]["to_stern"], AIS_DB[str(decoded.mmsi)]["to_port"], AIS_DB[str(decoded.mmsi)]["to_starboard"])
                            payload_target.position.latitude_degrees = latitude_adj
                            payload_target.position.longitude_degrees = longitude_adj
                                    

                    # Managing AIS within area of interest
                    if position_within_boundary(payload_target.position.latitude_degrees, payload_target.position.longitude_degrees, args):
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
                    
                    payload_target.trajectory_over_ground.speed_over_ground_knots = decoded.speed
                    payload_target.position.latitude_degrees = decoded.lat
                    payload_target.position.longitude_degrees = decoded.lon
                    payload_target.trajectory_over_ground.course_over_ground_degrees = decoded.course
                    payload_target.heading.heading_degrees = decoded.heading
                    
                    # Managing AIS within area of interest
                    if position_within_boundary(payload_target.position.latitude_degrees, payload_target.position.longitude_degrees, args):
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
           
                    if "shipname" in json_decoded:  # Part A
                        payload_target.description.vessel.information.name = decoded.shipname
                        
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
                      
                        payload_target.description.vessel.information.call_sign = decoded.callsign
                        payload_target.description.vessel.information.type = set_target_type_enum(decoded.ship_type)

                        width = decoded.to_port + decoded.to_starboard
                        length = decoded.to_bow + decoded.to_stern

                        new_to_bow = length / 2
                        new_to_stern = -length / 2
                        new_to_starboard = width / 2
                        new_to_port = -width / 2

                        payload_target.description.vessel.common_reference_point.distance_to_bow_meters = new_to_bow
                        payload_target.description.vessel.common_reference_point.distance_to_stern_meters = new_to_stern
                        payload_target.description.vessel.common_reference_point.distance_to_starboard_meters = new_to_starboard
                        payload_target.description.vessel.common_reference_point.distance_to_port_meters = new_to_port
                 

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
                        payload_target.description.vessel.information.name = AIS_DB[str(decoded.mmsi)]["shipname"]

                    if "position_within_boundary" in AIS_DB[str(decoded.mmsi)].keys():
                        if AIS_DB[str(decoded.mmsi)]["position_within_boundary"]:
                                                                      
                            logging.debug(f"PUBLISH payload_target: {payload_target}")
                            publish_message(payload_target, "target", decoded.mmsi, session, args, logging)
                            logging.debug(f"PUBLISH GeoJSON: {geojson}")
                            publish_message(geojson, "foxglove_geojson", decoded.mmsi, session, args, logging)

            # except Exception as e:
            #     logging.warning(f"Error parsing AIS: {e}")


def sub_digitraffic_data(data):
    logging.debug(f"Received on: {data.key_expr}")

    # logging.debug(f"Received data: {data.payload}") # Receiving plain json
    # json_string = data.payload.decode('utf-8')

    # # Convert the JSON string to a dictionary
    # data_dict = json.loads(json_string)

    # time_now = time.time_ns()
    # payload_target = Target()
    # payload_target.data_source.source.append(DataSource.Source.AIS_PROVIDER)
    # payload_target.timestamp.FromNanoseconds(time_now)
    # payload_target_description = TargetDescription()
    # payload_target_description.data_source.source.append(
    #     DataSource.Source.AIS_PROVIDER)
    # payload_target_description.timestamp.FromNanoseconds(time_now)

    # if str(data.key_expr).split("/")[-1] == "location":

    #     # logging.debug(f"Location: {data_dict}")

    #     mmsi = str(data.key_expr).split("/")[-2]
    #     payload_target.mmsi = int(mmsi)

    #     # NAVIGATIONN STATUS
    #     status = data_dict["navStat"]
    #     payload_target.navigation_status = set_navigation_status_enum(status)

    #     # ROT, SOG, COG, HDG
    #     payload_target.rate_of_turn_degrees_per_minute = data_dict["rot"]
    #     payload_target.speed_over_ground_knots = data_dict["sog"]
    #     payload_target.course_over_ground_knots = data_dict["cog"]
    #     payload_target.heading_degrees = data_dict["heading"]

    #     # Correcting AIS position if vessel outline is available
    #     if str(mmsi) in AIS_DB:
    #         if "to_stern" in AIS_DB[str(mmsi)].keys():
    #             logging.debug(f"Adjusting position for MMSI: {mmsi}")
    #             latitude_adj, longitude_adj = position_to_common_center_point(data_dict["lat"], data_dict["lon"], data_dict["heading"], AIS_DB[str(
    #                 mmsi)]["to_bow"], AIS_DB[str(mmsi)]["to_stern"], AIS_DB[str(mmsi)]["to_port"], AIS_DB[str(mmsi)]["to_starboard"])
    #             payload_target.latitude_degrees = latitude_adj
    #             payload_target.longitude_degrees = longitude_adj

    #             payload_target.position.latitude = latitude_adj
    #             payload_target.position.longitude = longitude_adj

    #     else:
    #         payload_target.latitude_degrees = data_dict["lat"]
    #         payload_target.longitude_degrees = data_dict["lon"]

    #     # Managing AIS within area of interest
    #     if position_within_boundary(payload_target.latitude_degrees, payload_target.longitude_degrees, args):
    #         # for AIS position correction

    #         if str(mmsi) in AIS_DB:
    #             AIS_DB[str(mmsi)] = {
    #                 **AIS_DB[str(mmsi)],
    #                 "position_within_boundary": True
    #             }
    #         else:
    #             AIS_DB[str(mmsi)] = {
    #                 "position_within_boundary": True
    #             }
    #         publish_message(
    #             payload_target, "target", mmsi, session, args, logging)
    #     else:
    #         if str(mmsi) in AIS_DB:
    #             AIS_DB[str(mmsi)] = {
    #                 **AIS_DB[str(mmsi)],
    #                 "position_within_boundary": False
    #             }
    #         else:
    #             AIS_DB[str(mmsi)] = {
    #                 "position_within_boundary": False
    #             }

    # elif str(data.key_expr).split("/")[-1] == "metadata":
    #     logging.debug(f"Metadata: {data_dict}")

    #     # MMSI
    #     mmsi = str(data.key_expr).split("/")[-2]
    #     payload_target.mmsi = int(mmsi)
    #     payload_target_description.mmsi = int(mmsi)

    #     payload_target_description.name = data_dict["name"]
    #     payload_target_description.callsign = data_dict["callSign"]
    #     payload_target_description.vessel_type = set_target_type_enum(
    #         data_dict["type"])
    #     payload_target_description.imo = data_dict["imo"]

    #     width = data_dict["refC"] + data_dict["refD"]
    #     length = data_dict["refB"] + data_dict["refA"]

    #     new_to_bow = length / 2
    #     new_to_stern = -length / 2
    #     new_to_starboard = width / 2
    #     new_to_port = -width / 2

    #     payload_target_description.to_bow_meters = new_to_bow
    #     payload_target_description.to_stern_meters = new_to_stern
    #     payload_target_description.to_starboard_meters = new_to_starboard
    #     payload_target_description.to_port_meters = new_to_port

    #     payload_target_description.destination = data_dict["destination"]
    #     payload_target_description.draft_meters = data_dict["draught"]
    #     payload_target_description.estimated_time_of_arrival = str(
    #         data_dict["eta"])

    #     # for AIS position correction
    #     if str(mmsi) in AIS_DB:
    #         AIS_DB[str(mmsi)] = {
    #             **AIS_DB[str(mmsi)],
    #             "to_bow": data_dict["refA"],
    #             "to_stern": data_dict["refB"],
    #             "to_starboard": data_dict["refD"],
    #             "to_port": data_dict["refC"]
    #         }
    #     else:
    #         AIS_DB[str(mmsi)] = {
    #             "to_bow": data_dict["refA"],
    #             "to_stern": data_dict["refB"],
    #             "to_starboard": data_dict["refD"],
    #             "to_port": data_dict["refC"],
    #             "position_within_boundary": False
    #         }

    #     # Managing AIS within area of interest
    #     if AIS_DB[str(mmsi)]["position_within_boundary"]:
    #         publish_message(payload_target_description, "target_description",
    #                         mmsi, session, args, logging)

    # else:
    #     logging.warning(f"Unknown data: {data_dict}")


if __name__ == "__main__":
    main()
