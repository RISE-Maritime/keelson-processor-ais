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
import pyais

from utilitis import set_navigation_status_enum, set_target_type_enum, position_to_common_center_point, filterAIS, rot_fix, publish_message

session = None
args = None

# Storing AIS dimensions for each MMSI for position correction
AIS_DB = {
    "example": {
        "to_bow": 50,
        "to_stern": 50,
        "to_starboard": 10,
        "to_port": 10,
    },
}


def sub_sjv_data(data):

    received_at, enclosed_at, content = keelson.uncover(data.payload)
    # logging.debug(f"Received at: {received_at} | Enclosed at: {enclosed_at} type {type(enclosed_at)}" )


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
                payload_target.data_source.source.append(DataSource.Source.AIS_PROVIDER)
                payload_target.timestamp.FromNanoseconds(enclosed_at)
                payload_target_description = TargetDescription()
                payload_target_description.data_source.source.append(DataSource.Source.AIS_PROVIDER)
                payload_target_description.timestamp.FromNanoseconds(enclosed_at)

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

                    publish_message(payload_target, "target",
                                    decoded.mmsi, session, args, logging)

                # TYPE 18: Standard Class B CS Position Report
                elif decoded.msg_type in [18]:

                    payload_target.speed_over_ground_knots = decoded.speed
                    payload_target.longitude_degrees = decoded.lon
                    payload_target.latitude_degrees = decoded.lat
                    payload_target.course_over_ground_knots = decoded.course
                    payload_target.heading_degrees = decoded.heading
                    publish_message(
                        payload_target, "target", decoded.mmsi, session, args, logging)

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
                    publish_message(payload_target_description, "target_description",
                                    decoded.mmsi, session, args, logging)

                else:
                    logging.debug(f"Decoded AIS message: {decoded}")

        except Exception as e:
            logging.warning(f"Error parsing AIS: {e}")


def sub_digitraffic_data(data):
    logging.debug(f"Received on: {data.key_expr}")

    # logging.debug(f"Received data: {data.payload}") # Receiving plain json
    json_string = data.payload.decode('utf-8')

    # Convert the JSON string to a dictionary
    data_dict = json.loads(json_string)

    if str(data.key_expr).split("/")[-1] == "metadata":
        logging.debug(f"Metadata: {data_dict}")

    elif str(data.key_expr).split("/")[-1] == "location":
        logging.debug(f"Location: {data_dict}")
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
