import argparse
from ipaddress import ip_address
import logging
import os
import sys
from atavism.devices import AirplayDevice, Chromecast, DeviceError
from atavism.dnssd import MDNSServiceDiscovery
from atavism.http import HLSServer
from atavism.video import find_ffmpeg, HLSVideo, SimpleVideo
from atavism import __version__

def main():
    parser = argparse.ArgumentParser(description='AppleTV Video Player')
    parser.add_argument('--find-devices', action='store_true',
                        help='Scan and report for AppleTV devices')
    parser.add_argument('--ip', help='IPv4 address of AppleTV to use')
    parser.add_argument('--send-direct', action='store_true',
                        help="Don't create an HLS stream, just send the file")
    parser.add_argument('--ffmpeg-binary-name', default='ffmpeg',
                        help='Name of ffmpeg binary to use')
    parser.add_argument('--ffmpeg-search-paths', help='Path(s) to search for ffmpeg binary')
    parser.add_argument('--hls-only', action='store_true', help='Just create an HLS stream')
    parser.add_argument('--chromecast', action='store_true', help='If an IP is supplied, is it for a Chromecast?')
    parser.add_argument('-v', nargs='*', help='Additional debug information')
    parser.add_argument('--version', action='store_true', help='Show version and exit')
    parser.add_argument('--log', help='Logfile to save output into')
    parser.add_argument('video', nargs='?', help="Video to stream")

    args = parser.parse_args()

    if args.version:
        print("atavism,  version {}".format(__version__))
        print("https://github.com/zathras777/atavism")
        sys.exit(0)

    if args.video is None and args.find_devices is False:
        print("You must supply a video filename unless --find-devices is used.")
        sys.exit(0)

    if args.video is not None and not os.path.exists(args.video):
        print("The file '{}' does not exist!".format(args.video))
        sys.exit(0)

    if args.hls_only and args.send_direct:
        print("You have used --send-direct and --hls-only. Sadly this app can't do both!")
        sys.exit(0)

    # Setup some simple logging
    logger = logging.getLogger()
    if args.v is not None:
        logger.setLevel(min(10, 30 - len(args.v) * 10))
    if args.log is not None:
        fh = logging.FileHandler(args.log)
        fh.setLevel(logger.level)
        logger.addHandler(fh)
    else:
        logger.addHandler(logging.StreamHandler())

    if not args.send_direct and args.find_devices is False:
        ffmpeg = find_ffmpeg(binary_name=args.ffmpeg_binary_name, paths=args.ffmpeg_search_paths)

    active_device = None
    devices = []

    if not args.hls_only:
        if args.find_devices is True or args.ip is None:
            print("Looking for devices...\n")
            dev_src = MDNSServiceDiscovery('_airplay._tcp.local', '_googlecast._tcp.local')
            if not dev_src.find_devices():
                print("Unable to locate any airplay devices. Exiting...")
                sys.exit(0)

            for ptr in dev_src.devices:

                if 'airplay' in ptr:
                    devices.append(AirplayDevice(dev_src.devices[ptr]))
                elif 'googlecast' in ptr:
                    devices.append(Chromecast(dev_src.devices[ptr]))

            for d in devices:
                print("    Found {}".format(d))
            print("\n Search complete.\n")

            if args.find_devices is True:
                for d in devices:
                    d.stop()
                sys.exit(0)

        elif args.ip is not None:
            if args.chromecast:
                devices = [Chromecast({'A': ip_address(args.ip.decode())})]
            else:
                devices = [AirplayDevice({'A': ip_address(args.ip.decode())})]

        if len(devices) > 1:
            for n in range(len(devices)):
                print("    {}. {}".format(n + 1, devices[n]))

            print("\nAs more than one device was found, please enter the number of the device to use:")
            while True:
                try:
                    input = raw_input
                except NameError:
                    pass
                num_str = input("Device to use (c to cancel): ")
                if num_str.lower() == 'c':
                    sys.exit(0)
                try:
                    num = int(num_str)
                except ValueError:
                    print("You need to enter a number!")
                    continue
                if 1 <= num <= len(devices):
                    active_device = devices[num - 1]
                    break
                print("Number must be between 1 and {}".format(len(devices)))
        else:
            active_device = devices[0]
    else:
        active_device = AirplayDevice()

    if not args.send_direct:
        video = HLSVideo(args.video)
        print("Creating the HLS stream... ")
        if not video.create_hls(active_device.width, active_device.height):
            print("Unable to create an HLS stream from '{}'".format(args.video))
            sys.exit(0)
        print("    done")

        if args.hls_only:
            video.cleanup = False
            print("\nHLS stream created in {}".format(video.directory))
            sys.exit(0)

        print("HLS stream created: {} segments...".format(video.segments))
    else:
        print("Getting video information...")
        video = SimpleVideo(args.video)
        print("    done")

    print("Duration: {} seconds\n".format(video.info.get('duration')))
    srv = HLSServer(video=video)
    srv.start()
    try:
        active_device.play_video(srv)
        while srv.running:
            try:
                srv.join()
            except KeyboardInterrupt:
                print("command_line: keyboard interrupt")
                break
    except DeviceError as e:
        print(e)
    srv.stop()
