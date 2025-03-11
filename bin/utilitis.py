from keelson.payloads.Target_pb2 import Target
from keelson.payloads.Vessel_pb2 import VesselInformation
from keelson.payloads.Navigation_pb2 import NavigationStatus
import geopy.distance
import keelson
import zenoh


def set_navigation_status_enum(status):
    if status == 0:
        return NavigationStatus.NavigationStatusType.UNDER_WAY
    elif status == 1:
        return NavigationStatus.NavigationStatusType.AT_ANCHOR
    elif status == 2:
        return NavigationStatus.NavigationStatusType.NOT_UNDER_COMMAND
    elif status == 3:
        return NavigationStatus.NavigationStatusType.RESTRICTED_MANEUVERABILITY
    elif status == 4:
        return NavigationStatus.NavigationStatusType.CONSTRAINED_BY_DRAUGHT
    elif status == 5:
        return NavigationStatus.NavigationStatusType.MOORED
    elif status == 6:
        return NavigationStatus.NavigationStatusType.AGROUND
    elif status == 7:
        return NavigationStatus.NavigationStatusType.ENGAGED_IN_FISHING
    elif status == 8:
        return NavigationStatus.NavigationStatusType.UNDER_WAY_SAILING
    elif status == 9:
        return NavigationStatus.NavigationStatusType.FUTURE_HSC
    elif status == 10:
        return NavigationStatus.NavigationStatusType.FUTURE_WIG
    elif status == 11:
        return NavigationStatus.NavigationStatusType.TOWING_ASTERN
    elif status == 12:
        return NavigationStatus.NavigationStatusType.PUSHING_AHEAD
    elif status == 13:
        return NavigationStatus.NavigationStatusType.RESERVED_FUTURE_USE
    elif status == 14:
        return NavigationStatus.NavigationStatusType.AIS_SART
    else:
        return NavigationStatus.NavigationStatusType.UNDEFINED


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
    # TYPE 1: Position Report Class A
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
    key_exp_pub_target = keelson.construct_pubsub_key(
        realm=args.realm,
        entity_id=args.entity_id,
        subject=subject,  # Needs to be a supported subject
        source_id="ais/"+str(mmsi),
    )
    pub = session.declare_publisher(
        key_exp_pub_target
    )

    # Publish the target
    serialized_payload_target = payload.SerializeToString()
    envelope_target = keelson.enclose(serialized_payload_target)
    pub.put(envelope_target)


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


def corrBering(bering):
    """
    Checking if bearing angle is insode 0 to 360

    Parameters
    ----------
    bering (float) : bering angle
    """

    if bering >= 0 or bering < 360:
        return bering
    elif bering >= 360:
        return bering - 360
    elif bering < 0:
        return bering + 360


def getPredictorPositionsByTime(
    predict_minutes, from_latitude, from_longitude, sog, cog, rot, heading, num_of_predictions=10
):
    """
    Predictor positions and headings

    Parameters
    ----------
    predict_minutes (float) : predicted time forward
    num_of_predictions (int) : positions that will be returned
    latitude (float) : own ship latitude given in degrees
    longitude (float) :  own ship longitude given in degrees
    sog (float) : own ship speed in knots
    cog (float) : true north course over graound in (Degrees 0-360)
    rot (float) : turning rate (Degrees per minute)
    heading (float) : own ships heading
    """

    heading_predictions = []
    pos_predictions = []

    time_step = predict_minutes / num_of_predictions
    pos_step = [from_latitude, from_longitude]

    for pred_num in range(1, num_of_predictions + 1):
        predict_minutes = time_step * pred_num

        # Heading prediction
        heading_change_prediction = heading + (rot * predict_minutes)
        heading_change_prediction = corrBering(heading_change_prediction)
        heading_predictions.append(heading_change_prediction)

        # Position prediction
        distance_traveled = sog * (time_step / 60)
        cog_dir_prediction = cog + (rot * predict_minutes)
        pos_prediction = list(
            geopy.distance.distance(nautical=distance_traveled).destination(
                (pos_step[0], pos_step[1]), bearing=cog_dir_prediction
            )
        )
        pos_predictions.append([pos_prediction[1], pos_prediction[0]])
        pos_step = [pos_prediction[0], pos_prediction[1]]

    return pos_predictions, heading_predictions
