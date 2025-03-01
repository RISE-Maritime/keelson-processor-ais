from keelson.payloads.Target_pb2 import Target
from keelson.payloads.Vessel_pb2 import VesselInformation
import geopy.distance
import keelson
import zenoh


def set_navigation_status_enum(status):
    if status == 0:
        return Target.NavigationStatus.UNDER_WAY
    elif status == 1:
        return Target.NavigationStatus.AT_ANCHOR
    elif status == 2:
        return Target.NavigationStatus.NOT_UNDER_COMMAND
    elif status == 3:
        return Target.NavigationStatus.RESTRICTED_MANEUVERABILITY
    elif status == 4:
        return Target.NavigationStatus.CONSTRAINED_BY_DRAUGHT
    elif status == 5:
        return Target.NavigationStatus.MOORED
    elif status == 6:
        return Target.NavigationStatus.AGROUND
    elif status == 7:
        return Target.NavigationStatus.ENGAGED_IN_FISHING
    elif status == 8:
        return Target.NavigationStatus.UNDER_WAY_SAILING
    elif status == 9:
        return Target.NavigationStatus.FUTURE_HSC
    elif status == 10:
        return Target.NavigationStatus.FUTURE_WIG
    elif status == 11:
        return Target.NavigationStatus.TOWING_ASTERN
    elif status == 12:
        return Target.NavigationStatus.PUSHING_AHEAD
    elif status == 13:
        return Target.NavigationStatus.RESERVED_FUTURE_USE
    elif status == 14:
        return Target.NavigationStatus.AIS_SART
    elif status == 15:
        return Target.NavigationStatus.UNDEFINED


def set_target_type_enum(target_type):
    if target_type == 0:
        return VesselInformation.VesselType.UNKNOWN
    elif target_type == 20:
        return VesselInformation.VesselType.WIG
    elif target_type == 30:
        return VesselInformation.VesselType.FISHING
    elif target_type == 31:
        return VesselInformation.VesselType.TOWING
    elif target_type == 32:
        return VesselInformation.VesselType.TOWING_LONG
    elif target_type == 33:
        return VesselInformation.VesselType.DREDGING
    elif target_type == 34:
        return VesselInformation.VesselType.DIVING
    elif target_type == 35:
        return VesselInformation.VesselType.MILITARY
    elif target_type == 36:
        return VesselInformation.VesselType.SAILING
    elif target_type == 37:
        return VesselInformation.VesselType.PLEASURE
    elif target_type == 40:
        return VesselInformation.VesselType.HSC
    elif target_type == 50:
        return VesselInformation.VesselType.PILOT
    elif target_type == 51:
        return VesselInformation.VesselType.SAR
    elif target_type == 52:
        return VesselInformation.VesselType.TUG
    elif target_type == 53:
        return VesselInformation.VesselType.PORT
    elif target_type == 54:
        return VesselInformation.VesselType.ANTI_POLLUTION
    elif target_type == 55:
        return VesselInformation.VesselType.LAW_ENFORCEMENT
    elif target_type == 58:
        return VesselInformation.VesselType.MEDICAL
    elif target_type == 60:
        return VesselInformation.VesselType.PASSENGER
    elif target_type == 70:
        return VesselInformation.VesselType.CARGO
    elif target_type == 80:
        return VesselInformation.VesselType.TANKER
    else:
        return VesselInformation.VesselType.OTHER


def position_to_common_center_point(latitude, longitude, heading, to_bow, to_stern, to_port, to_starboard):
    # Longitudinal
    midpointL = (to_bow + to_stern) / 2
    if midpointL > to_bow:
        move_long = to_bow - midpointL
    elif midpointL < to_bow:
        move_long = to_bow - midpointL
    else:
        move_long = 0

    # Lateral
    midpointV = (to_starboard + to_port) / 2
    if midpointV > to_starboard:
        move_lat = to_starboard - midpointV
    elif midpointV < to_starboard:
        move_lat = to_starboard - midpointV
    else:
        move_lat = 0

    point_long_adj = geopy.distance.distance(meters=move_long).destination(
        (latitude, longitude), bearing=heading)
    point_final = geopy.distance.distance(meters=move_lat).destination(
        (point_long_adj.latitude, point_long_adj.longitude), bearing=heading+90)

    return point_final.latitude, point_final.longitude


def filterAIS(msg):
    # Filter out AIS messages

    # TYPE 0: Unknown
    # TYPE 4: Base Station Report
    # TYPE 8: Binary Broadcast Message
    # TYPE 9: Standard SAR Aircraft Position Report
    # TYPE 20: Data Link Management
    # TYPE 21: Aid-to-Navigation Report
    # TYPE 27: Long Range AIS Broadcast message
    if msg.msg_type in [0, 4, 8, 9, 20, 21, 27]:
        return False
    else:
        return True


def rot_fix(rot):
    if 127 >= rot <= -127:
        rot = 0
        return rot
    else:
        return rot


def publish_message(payload, subject: str, mmsi, session, args, logging):
    # Target publisher
    key_exp_pub_target = keelson.construct_pub_sub_key(
        realm=args.realm,
        entity_id=args.entity_id,
        subject=subject,  # Needs to be a supported subject
        source_id="ais/"+str(mmsi),
    )
    pub_target = session.declare_publisher(
        key_exp_pub_target,
        priority=zenoh.Priority.BACKGROUND(),
        congestion_control=zenoh.CongestionControl.DROP(),
    )
    logging.debug(f"Created publisher: {key_exp_pub_target}")
    logging.debug(f"Publisher payload: {payload}")

    # Publish the target
    serialized_payload_target = payload.SerializeToString()
    envelope_target = keelson.enclose(serialized_payload_target)
    pub_target.put(envelope_target)


def position_within_boundary(latitude: float, longitude: float, args):
    """
    Check if a position is within the boundary

    :param latitude: Latitude of the position
    :param longitude: Longitude of the position
    :param args: Arguments from the terminal
    
    :return: True if within boundary, False if outside boundary

    """
    if args.boundary_north >= latitude >= args.boundary_south and args.boundary_east >= longitude >= args.boundary_west:
        return True
    else:
        return False
