from keelson.payloads.Target_pb2 import Target

if __name__ == '__main__':
    target = Target()
    
    target.mmsi = 123456789
    target.navigation_status = Target.NavigationStatus.AGROUND
    print(target.ListFields())

    print(target)