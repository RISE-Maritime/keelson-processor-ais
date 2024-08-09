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
from keelson.payloads.Target_pb2 import Target, TargetDescription
import pyais

from utilitis import set_navigation_status_enum, set_target_type_enum, position_to_common_center_point

session = None
args = None
pub_target = None
pub_target_description = None

AIS_DB = {
    "example": {
        "to_bow": 50,
        "to_stern": 50,
        "to_starboard": 10,
        "to_port": 10,
    },
}


def filterAIS(msg):
    # Filter out AIS messages

    # TYPE 4: Base Station Report
    # TYPE 8: Binary Broadcast Message
    # TYPE 9: Standard SAR Aircraft Position Report
    # TYPE 20: Data Link Management
    # TYPE 21: Aid-to-Navigation Report
    # TYPE 27: Long Range AIS Broadcast message
    if msg.msg_type in [0, 4, 8, 9, 20, 21, 27]:
        return False

    return True


def rot_fix(rot):
    if 127 >= rot <= -127:
        rot = 0
        return rot
    else:
        return rot


def sub_sjv_data(data):

    received_at, enclosed_at, content = keelson.uncover(data.payload)
    # logging.debug(f"Received on: {data.key_expr}")
    time_value = TimestampedBytes.FromString(content)
    # logging.debug(f"Received data: {time_value}")

    # Parse the NMEA0183 AIS data
    nmea_sentence = time_value.value.decode("utf-8")

    if nmea_sentence.split(",")[0] not in ["!AIVDM", "$ABVSI"]:
        # logging.debug(f"Received NMEA sentence: {nmea_sentence}")

        try:
            decoded = pyais.decode(nmea_sentence)

            if filterAIS(decoded):
                payload_target = Target()
                payload_target_description = TargetDescription()

                # MMSI
                payload_target.mmsi = decoded.mmsi
                payload_target_description.mmsi = decoded.mmsi

                # TYPE 1,2 & 3: Position Report Class A
                # TYPE 27: Long Range AIS Broadcast message
                if decoded.msg_type in [1, 2, 3, 27]:

                    # NAVIGATIONN STATUS
                    status = decoded.status.value
                    payload_target_description.navigation_status = set_navigation_status_enum(
                        status)
                    # logging.debug(f"Payload_target_description: {TargetDescription.NavigationStatus.Name(payload_target_description.navigation_status)}")

                    # ROT
                    rot = pyais.messages.from_turn(decoded.turn)
                    rot = rot_fix(rot)
                    payload_target.rate_of_turn_degrees_per_minute = rot
                    payload_target.speed_over_ground_knots = decoded.speed
                    payload_target.course_over_ground_knots = decoded.course
                    payload_target.heading_degrees = decoded.heading

                    if AIS_DB.get(str(decoded.mmsi)):
                        latitude_adj, longitude_adj = position_to_common_center_point(decoded.lat, decoded.lon, decoded.heading, AIS_DB[str(
                            decoded.mmsi)]["to_bow"], AIS_DB[str(decoded.mmsi)]["to_stern"], AIS_DB[str(decoded.mmsi)]["to_port"], AIS_DB[str(decoded.mmsi)]["to_starboard"])
                        payload_target.latitude_degrees = latitude_adj
                        payload_target.longitude_degrees = longitude_adj
                    else:
                        payload_target.latitude_degrees = decoded.lat
                        payload_target.longitude_degrees = decoded.lon

                # TYPE 18: Standard Class B CS Position Report
                elif decoded.msg_type in [18]:

                    payload_target.speed_over_ground_knots = decoded.speed
                    payload_target.longitude_degrees = decoded.lon
                    payload_target.latitude_degrees = decoded.lat
                    payload_target.course_over_ground_knots = decoded.course
                    payload_target.heading_degrees = decoded.heading

                elif decoded.msg_type in [24]:  # TYPE 24: Static Data Report
                    json_decoded = decoded.to_json()
                    # logging.debug(f"Decoded AIS message: {decoded}")

                    if "shipname" in json_decoded:  # Part A
                        payload_target_description.name = decoded.shipname
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
                        AIS_DB[str(decoded.mmsi)] = {
                            "to_bow": decoded.to_bow,
                            "to_stern": decoded.to_stern,
                            "to_starboard": decoded.to_starboard,
                            "to_port": decoded.to_port,
                        }

                else:
                    logging.debug(f"Decoded AIS message: {decoded}")

                logging.debug(f"Target: {payload_target}")

                #################################################
                # Setting up PUBLISHER

                # Target publisher
                key_exp_pub_target = keelson.construct_pub_sub_key(
                    realm=args.realm,
                    entity_id=args.entity_id,
                    subject="target",  # Needs to be a supported subject
                    source_id="ais/"+str(decoded.mmsi),
                )
                pub_target = session.declare_publisher(
                    key_exp_pub_target,
                    priority=zenoh.Priority.BACKGROUND(),
                    congestion_control=zenoh.CongestionControl.DROP(),
                )
                logging.info(f"Created publisher: {key_exp_pub_target}")

                # Publish the target
                serialized_payload_target = payload_target.SerializeToString()
                envelope_target = keelson.enclose(serialized_payload_target)
                pub_target.put(envelope_target)



                # Target description publisher
                key_exp_pub_target_description = keelson.construct_pub_sub_key(
                    realm=args.realm,
                    entity_id=args.entity_id,
                    subject="target_description",  # Needs to be a supported subject
                    source_id="ais/"+str(decoded.mmsi),
                )
                pub_target_description = session.declare_publisher(
                    key_exp_pub_target_description,
                    priority=zenoh.Priority.BACKGROUND(),
                    congestion_control=zenoh.CongestionControl.DROP(),
                )
                logging.info(f"Created publisher: {key_exp_pub_target_description}")
                logging.debug(f"Description: {payload_target_description}")
                # Publish the target description
                serialized_payload_target_description = payload_target_description.SerializeToString()
                envelope_target_description = keelson.enclose(
                    serialized_payload_target_description)
                pub_target_description.put(envelope_target_description)


        except Exception as e:
            logging.warning(f"Error parsing AIS: {e}")


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

 
    #################################################
    # Setting up SUBSCRIBERs

    # Sjöfartsverket AIS subscriber
    key_exp_pub_raw = keelson.construct_pub_sub_key(
        realm=args.realm,
        entity_id="sjofartsverket",
        subject="raw/ais/nmea0183",  # Needs to be a supported subject
        source_id="**",
    )
    sub_raw = session.declare_subscriber(
        key_exp_pub_raw,
        sub_sjv_data,
    )
    logging.debug(f"Subscribing to: {key_exp_pub_raw}")

    # try:

      
    # except KeyboardInterrupt:
    #     logging.info("Closing down on user request!")
    #     # Close the socket
    #     logging.debug("Done! Good bye :)")
