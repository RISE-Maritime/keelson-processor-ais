# Keelson Processor AIS

Keelson Processor AIS is a tool designed to process Automatic Identification System (AIS) data. It provides a flexible way to handle AIS messages from different providers, enabling users to publish and subscribe to various data streams. This README will guide you through the setup and usage of the Keelson Processor AIS, including quick start instructions, processing data, and setting up a development environment.

´´´´´´´´´

## Quick start

```bash
python3 bin/main.py --log-level 10 -r rise -e ted --publish udp_sjv --subscribe sjofartsverket 

python3 bin/main.py --log-level 20 -r rise -e erik --publish udp_sjv --subscribe sjofartsverket 

python3 bin/main.py --log-level 10 -r rise -e ted --publish log --subscribe digitraffic 

python3 bin/main.py --log-level 10 -r rise -e ted --publish sjv_nmea_udp --udp-port 10110 --subscribe sjofartsverket

python3 bin/main.py --log-level 30 -r rise -e ted --publish sjv_nmea_os_udp --os_mmsi 230361000 --udp-port 10110 --subscribe sjofartsverket --publish sjv_nmea_ais_udp

python3 bin/main.py --log-level 10 -r rise -e ted  --subscribe sjofartsverket --publish sjv_targets

python3 bin/main.py --log-level 10 -r rise -e ted  --subscribe sjofartsverket --publish sjv_targets
python3 bin/main.py --log-level 10 -r rise -e ted  --subscribe sjofartsverket --publish sjv_targets -bn 57.7 -bw 11.3 -bs 57.2 -be 12.7



vscode ➜ /workspaces/keelson-processor-ais (master) $ python3 bin/main.py -h

usage: keelson_processor_ais [-h] [-l LOG_LEVEL] [--mode {peer,client}] [--connect CONNECT] [-r REALM] [-e ENTITY_ID] --subscribe {sjofartsverket,digitraffic}
                             [--publish {log,sjv_nmea_ais_udp,sjv_nmea_os_udp,sjv_raw_udp,target}] [--udp-port UDP_PORT] [--udp-host UDP_HOST] [--os_mmsi OS_MMSI] [-bn BOUNDARY_NORTH] [-bs BOUNDARY_SOUTH]
                             [-be BOUNDARY_EAST] [-bw BOUNDARY_WEST]

options:
  -h, --help            show this help message and exit
  -l LOG_LEVEL, --log-level LOG_LEVEL
                        Log level 10=DEBUG, 20=INFO, 30=WARN, 40=ERROR, 50=CRITICAL 0=NOTSET (default: 30)
  --mode {peer,client}, -m {peer,client}
                        The zenoh session mode. (default: None)
  --connect CONNECT     Endpoints to connect to, in case multicast is not working. ex. tcp/localhost:7447 (default: None)
  -r REALM, --realm REALM
                        Unique id for a domain/realm to connect ex. rise (default: rise)
  -e ENTITY_ID, --entity-id ENTITY_ID
                        Entity being a unique id representing an entity within the realm ex, landkrabba (default: masslab)
  --subscribe {sjofartsverket,digitraffic}
                        The keelson AIS data source to subscribe to, allowing multiple sources by specifying multiple subscribers. (default: None)
  --publish {log,sjv_nmea_ais_udp,sjv_nmea_os_udp,sjv_raw_udp,target}
  --udp-port UDP_PORT   UDP port to send NMEA data to (default: 10110)
  --udp-host UDP_HOST   UDP host to send NMEA data to (default: 127.0.0.1)
  --os_mmsi OS_MMSI     MMSI of the own ship (default: None)
  -bn BOUNDARY_NORTH, --boundary_north BOUNDARY_NORTH
                        Northern boundary of the area of interest (default: 63.9)
  -bs BOUNDARY_SOUTH, --boundary_south BOUNDARY_SOUTH
                        Southern boundary of the area of interest (default: 62.8)
  -be BOUNDARY_EAST, --boundary_east BOUNDARY_EAST
                        Eastern boundary of the area of interest (default: 21.7)
  -bw BOUNDARY_WEST, --boundary_west BOUNDARY_WEST
                        Western boundary of the area of interest (default: 20.293)



```


## Record 
´´´´´
```bash
docker run --rm --network host --name ais-udp ghcr.io/rise-maritime/keelson-processor-ais:0.0.3 "keelson-processor-ais -r rise -e erik --publish udp_sjv --subscribe sjofartsverket"


sudo docker run --rm --network host  --name mcap-logger --volume ~/rec:/rec ghcr.io/rise-maritime/keelson:0.3.7-pre.51 "keelson_processor_ais --output_path rec -k rise/v0/ted/**"

```

 --mode client --connect tcp/10.10.7.2:7448


Setup for development environment on your own computer: ´

1) Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
   - Docker desktop will provide you with an UI ´´for monitoring and controlling docker containers and images along debugging 
   - If you want to learn more about docker and its building blocks of images and containers checkout [Docker quick hands-on in guide](https://docs.docker.com/guides/get-started/)
2) Start up of **Zenoh router** either in your computer or any other computer within your local network 

   ```bash
    # Navigate to folder containing docker-compose.zenoh-router.yml
  
    # Start router with log output 
    docker-compose -f containing docker-compose.zenoh-router.yml up 

    # If no obvious errors, stop container "ctrl-c"

    # Start container and let it run in the background/detached (append -d) 
    docker-compose -f containing docker-compose.zenoh-router.yml up -d
   ```

    [Link to --> docker-compose.zenoh-router.yml](docker-compose.zenoh-router.yml)

1) Now the Zenoh router is hopefully running in the background and should be available on localhost:8000. This can be example tested with [Zenoh Rest API ](https://zenoh.io/docs/apis/rest/) or continue to next step running Python API
2) Set up python virtual environment  `python >= 3.11`
   1) Install package `pip install -r requirements.txt`
3)  Now you are ready to explore some example scripts in the [exploration folder](./exploration/) 
    1)  Sample are coming from:
         -   [Zenoh Python API ](https://zenoh-python.readthedocs.io/en/0.10.1-rc/#quick-start-examples)


[Zenoh CLI for debugging and problem solving](https://github.com/RISE-Maritime/zenoh-cli)




UDP 1830 



## Start UDP AIS stream on port 1830

Step 1: Set up configuration file

- Make a folder for Keelson connectors and processors:
  - Copy a docker compose file [docker-compose.ais-processor.yml](./docker-compose.ais-processor.yml) OR create a file with name "docker-compose.ais-processor.yml" and add content bellow 

```yml
services:

  keelson-processor-ais:
    image: ghcr.io/rise-maritime/keelson-processor-ais:latest
    container_name: keelson-processor-ais
    restart: unless-stopped
    network_mode: "host"
    command: "--log-level 10 --publish udp_sjv --subscribe sjofartsverket"
```

Step 2: Set up docker service configuration

- Open a terminal and navigate to location where you created the file
- Run following start up command in a terminal to start the service
  
  ```bash
  docker compose -f docker-compose.ais-processor.yml up -d
  ```

- Docker images will be downloaded and service started 

Step 3: Open Docker Desktop

- Check if you can find the new service in docker desktop
- From now on you can start and stop the service from docker desktop (You do not need to do the step 2 again)  
