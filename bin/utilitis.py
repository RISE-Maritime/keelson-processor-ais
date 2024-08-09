from keelson.payloads.Target_pb2 import TargetDescription
import geopy.distance


def set_navigation_status_enum(status):
      if status == 0:
          return TargetDescription.NavigationStatus.UNDER_WAY
      elif status == 1:
          return TargetDescription.NavigationStatus.AT_ANCHOR
      elif status == 2:
          return TargetDescription.NavigationStatus.NOT_UNDER_COMMAND
      elif status == 3:
          return TargetDescription.NavigationStatus.RESTRICTED_MANEUVERABILITY
      elif status == 4:
          return TargetDescription.NavigationStatus.CONSTRAINED_BY_DRAUGHT
      elif status == 5:
          return TargetDescription.NavigationStatus.MOORED
      elif status == 6:
          return TargetDescription.NavigationStatus.AGROUND
      elif status == 7:
          return TargetDescription.NavigationStatus.ENGAGED_IN_FISHING
      elif status == 8:
          return TargetDescription.NavigationStatus.UNDER_WAY_SAILING
      elif status == 9:
          return TargetDescription.NavigationStatus.FUTURE_HSC
      elif status == 10:
          return TargetDescription.NavigationStatus.FUTURE_WIG
      elif status == 11:
          return TargetDescription.NavigationStatus.TOWING_ASTERN
      elif status == 12:
          return TargetDescription.NavigationStatus.PUSHING_AHEAD
      elif status == 13:
          return TargetDescription.NavigationStatus.RESERVED_FUTURE_USE
      elif status == 14:
          return TargetDescription.NavigationStatus.AIS_SART
      elif status == 15:
          return TargetDescription.NavigationStatus.UNDEFINED
      
def set_target_type_enum(target_type):
    if target_type == 0:
        return TargetDescription.TargetType.UNKNOWN
    elif target_type == 20:
        return TargetDescription.TargetType.WIG
    elif target_type == 30:
        return TargetDescription.TargetType.FISHING
    elif target_type == 31:
        return TargetDescription.TargetType.TOWING
    elif target_type == 32:
        return TargetDescription.TargetType.TOWING_LONG
    elif target_type == 33:
        return TargetDescription.TargetType.DREDGING
    elif target_type == 34:
        return TargetDescription.TargetType.DIVING
    elif target_type == 35:
        return TargetDescription.TargetType.MILITARY
    elif target_type == 36:
        return TargetDescription.TargetType.SAILING
    elif target_type == 37:
        return TargetDescription.TargetType.PLEASURE
    elif target_type == 40:
        return TargetDescription.TargetType.HSC
    elif target_type == 50:
        return TargetDescription.TargetType.PILOT
    elif target_type == 51:
        return TargetDescription.TargetType.SAR
    elif target_type == 52:
        return TargetDescription.TargetType.TUG
    elif target_type == 53:
        return TargetDescription.TargetType.PORT
    elif target_type == 54:
        return TargetDescription.TargetType.ANTI_POLLUTION
    elif target_type == 55:
        return TargetDescription.TargetType.LAW_ENFORCEMENT
    elif target_type == 58:
        return TargetDescription.TargetType.MEDICAL
    elif target_type == 60:
        return TargetDescription.TargetType.PASSENGER
    elif target_type == 70:
        return TargetDescription.TargetType.CARGO
    elif target_type == 80:
        return TargetDescription.TargetType.TANKER
    else:
        return TargetDescription.TargetType.OTHER
        


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

  point_long_adj = geopy.distance.distance(meters=move_long).destination((latitude, longitude), bearing=heading)
  point_final = geopy.distance.distance(meters=move_lat).destination((point_long_adj.latitude, point_long_adj.longitude), bearing=heading+90)

  return point_final.latitude, point_final.longitude 
    
