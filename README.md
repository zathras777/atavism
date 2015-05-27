_**atavism** - an evolutionary throwback._

# atavism
Python module and script to allow playing videos to an AppleTV or Chromecast.

## Usage

> $ atavism ~/Videos/some_video.mp4

The output is simple :-)

```
 Looking for devices...

     Found Apple TV [AppleTV3,2]  1920x1080 @ 192.168.xxxxxxx:7000

 Search complete.

 Creating the HLS stream...
     done
 HLS stream created: 4 segments...

    Playback: [###                                               ]   7.031%
    Playback: [#####                                             ]  11.081%
    Playback: [########                                          ]  16.117%
    Playback: [##########                                        ]  21.151%
    Playback: [#############                                     ]  26.690%
    Playback: [###############                                   ]  31.725%
    Playback: [##################                                ]  36.760%
    Playback: [####################                              ]  41.796%
    Playback: [#######################                           ]  46.834%
    Playback: [#########################                         ]  51.866%
    Playback: [############################                      ]  56.904%
    Playback: [##############################                    ]  61.937%
    Playback: [#################################                 ]  66.972%
    Playback: [####################################              ]  72.007%
    Playback: [######################################            ]  77.043%
    Playback: [#########################################         ]  82.078%
    Playback: [###########################################       ]  87.113%
    Playback: [##############################################    ]  92.148%
    Playback: [################################################  ]  97.183%
    Playback: [ Completed                                        ] 100.000%
```

This will look for ffmpeg and AppleTV or Chromecast devices on your network. If more than one is found a list should be
shown allowing you to choose which to use. 

Presently the app will create an HLS stream to stream to the device. This step can take a while and so direct streaming
is also supported using the --send-direct flag.

> $ atavism --send-direct ~/Videos/some_video.mp4

NB Whether the video is played depends on the support offered by the device.

> $ atavism --hls-only ~/Videos/some_video.mp4

This simply creates the HLS files in a directory and exits. No attempt will be made to find a suitable device.

## Usage Examples

If you know the IP address of an AppleTV...

> $ atavism --ip 192.168.55.55 Video.mp4

Or, if the device is a Chromecast...

> $ atavism --ip 192.168.55.55 --chromecast Video.mp4

To log some additional debug output...
 
> $ atavism --log some.log -v ...

## Background
This module started with a desire for a way to play a video file on the TV using the AppleTV - from the command line. The
original version of this app supported just teh AppleTV, but later versions (0.2 onwards) have also supported streaming
to a Chromecast.

The external HTTP interface of the AppleTV isn't documented, but there is unofficial information available, primarily at 
http://nto.github.io/AirPlay.html, which allowed me to write this.
The Chromecast code shown here uses the Google cast API, which is documented but without the work of many people in the
open source world I wouldn't have been able to add support.

## Why HLS?
Creating the HLS stream takes time and delays the start of playback, so why use it? The simple answer is that for large files, once created it starts the playback faster. Additionally, while the stream is being created the video is correctly encoded, allowing a far wider range of formats to be played via the AppleTV than is possible when sending the files directly.

## Status
It plays video files via an AppleTV or Chromecast device. 

The http module is still a work in progress. It may see more development depending on how my time go and it's use in some of my other projects. It's bundled here to reduce dependency issues.

Basic logging support has been added, but this needs to be expanded to be more useful.

The tests provide only a basic coverage, but are useful.

As always, feedback is welcome and contributions doubly so!

## Todo
* I really need to add logging support to see what's going on when it doesn't work as expected.
* The progress bar doesn't work as it should under Python3.

## Notes
* For HLS support this module requires a recent build of ffmpeg.

## Future Plans
This was written for my own use, but there are a few things I have considered for the future. If anyone else finds this useful, that may help with my time planning :-)

* Improve the code :-)
* Add more logging