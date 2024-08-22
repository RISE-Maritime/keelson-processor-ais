import argparse


def terminal_inputs():
    """Parse the terminal inputs and return the arguments"""

    parser = argparse.ArgumentParser(
        prog="keelson_processor_ais",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-l",
        "--log-level",
        type=int,
        default=30,
        help="Log level 10=DEBUG, 20=INFO, 30=WARN, 40=ERROR, 50=CRITICAL 0=NOTSET",
    )

    parser.add_argument(
        "--mode",
        "-m",
        dest="mode",
        choices=["peer", "client"],
        type=str,
        help="The zenoh session mode.",
    )

    parser.add_argument(
        "--connect",
        action="append",
        type=str,
        help="Endpoints to connect to, in case multicast is not working.",
    )

    parser.add_argument(
        "-r",
        "--realm",
        default="rise",
        type=str,
        help="Unique id for a domain/realm to connect ex. rise",
    )

    parser.add_argument(
        "-e",
        "--entity-id",
        default="masslab",
        type=str,
        help="Entity being a unique id representing an entity within the realm ex, landkrabba",
    )

    parser.add_argument(
        "--subscribe",
        choices=["sjofartsverket", "digitraffic"],
        type=str,
        required=True,
        action="append",
        help="The keelson AIS data source to subscribe to, allowing multiple sources by specifying multiple subscribers.",
    )

    parser.add_argument(
        "--publish",
        choices=["log"],
        type=str,
        required=False,
        action="append",
    )

    parser.add_argument(
        "-bn",
        "--boundary_north",
        type=float,
        required=False,
        default=63.9,
        help="Northern boundary of the area of interest",
    )

    parser.add_argument(
        "-bs",
        "--boundary_south",
        type=float,
        required=False,
        default=62.8,
        help="Southern boundary of the area of interest",
    )

    parser.add_argument(
        "-be",
        "--boundary_east",
        type=float,
        required=False,
        default=21.7,
        help="Eastern boundary of the area of interest",
    )

    parser.add_argument(
        "-bw",
        "--boundary_west",
        type=float,
        required=False,
        default=20.293,
        help="Western boundary of the area of interest",
    )

    # Parse arguments and start doing our thing
    args = parser.parse_args()

    return args
