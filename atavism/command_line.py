import argparse
import os
import sys
from atavism.devices import AirplayDevice
from atavism.dnssd import MDNSServiceDiscovery
from atavism.http import HLSServer
from atavism.video import find_ffmpeg, HLSVideo, SimpleVideo


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
    parser.add_argument('video', nargs='?', help="Video to stream")

    args = parser.parse_args()

    if args.video is None and args.find_devices is False:
        print("You must supply a video filename unless --find-devices is used.")
        sys.exit(0)

    if args.video is not None and not os.path.exists(args.video):
        print("The file '{}' does not exist!".format(args.video))
        sys.exit(0)

    if args.hls_only and args.send_direct:
        print("You have used --send-direct and --hls-only. Sadly this app can't do both!")
        sys.exit(0)

    if not args.send_direct and args.find_devices is False:
        ffmpeg = find_ffmpeg(binary_name=args.ffmpeg_binary_name, paths=args.ffmpeg_search_paths)

    active_device = None
    devices = []

    if not args.hls_only:
        if args.find_devices is True or args.ip is None:
            print("Looking for airplay devices...\n")
            dev_src = MDNSServiceDiscovery('_airplay._tcp.local')
            if not dev_src.find_devices():
                print("Unable to locate any airplay devices. Exiting...")
                sys.exit(0)

            devices = [AirplayDevice(dev_src.devices[ptr]) for ptr in dev_src.devices]
            for d in devices:
                print("    Found {}".format(d))
            print("\n Search complete.\n")

            if args.find_devices is True:
                for d in devices:
                    d.stop()
                sys.exit(0)

        elif args.ip is not None:
            devices = [AirplayDevice({'host': args.ip})]

        if len(devices) > 1:
            print("\nAs more than one device was found, please enter the number of the device to use:")
            print("\nHmm, maybe I should add this? :-)\n")
            active_device = devices[0]
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
        video = SimpleVideo(args.video)

    srv = HLSServer(video=video)
    srv.start()
    active_device.play_video(srv)
    while srv.running:
        try:
            srv.join()
        except KeyboardInterrupt:
            print("command_line: keyboard interrupt")
            break
    srv.stop()
