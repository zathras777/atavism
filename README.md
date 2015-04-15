# atavism
Python module and script to allow playing videos to an AppleTV

_**atavism** - an evolutionary throwback._

## Usage

> $ atavism ~/Videos/some_video.mp4

The output is simple :-)

> Looking for airplay devices...
>
>     Found Apple TV [AppleTV3,2]  1920x1080 @ 192.168.xxxxxxx:7000
>
>  Search complete.
>
> Creating the HLS stream...
>     done
> HLS stream created: 4 segments...
>
>    Playback: [#####                                             ] 11.081%
>    Playback: [########                                          ] 16.117%
>    Playback: [##########                                        ] 21.151%
>    Playback: [#############                                     ] 26.690%
>    Playback: [###############                                   ] 31.725%
>    Playback: [##################                                ] 36.760%
>    Playback: [####################                              ] 41.796%
>    Playback: [#######################                           ] 46.834%
>    Playback: [#########################                         ] 51.866%
>    Playback: [############################                      ] 56.904%
>    Playback: [##############################                    ] 61.937%
>    Playback: [#################################                 ] 66.972%
>    Playback: [####################################              ] 72.007%
>    Playback: [######################################            ] 77.043%
>    Playback: [#########################################         ] 82.078%
>    Playback: [###########################################       ] 87.113%
>    Playback: [##############################################    ] 92.148%
>    Playback: [################################################  ] 97.183%
>    Playback: [ Completed                                        ] 100.000%
>

This will look for ffmpeg and an AppleTV. Finding both it will create an HLS stream and then send it to the AppleTV.

> $ atavism --send-direct ~/Videos/some_video.mp4

As above, but no HLS stream will be created (ffmpeg is not required). Whether the video is played depends on it's suitability for the AppleTV.

> $ atavism --hls-only ~/Videos/some_video.mp4

This simply creates the HLS files in a directory and exits. No attempt will be made to find an AppleTV.

## Background
This module started with a desire for a way to play a video file on the TV using the AppleTV - from the command line.

The external HTTP interface of the AppleTV isn't documented, but there is unofficial information available, primarily at http://nto.github.io/AirPlay.html, which allowed me to write this.

## Why HLS?
Creating the HLS stream takes time and delays the start of playback, so why use it? The simple answer is that for large files, once created it starts the playback faster. Additionally, while the stream is being created the video is correctly encoded, allowing a far wider range of formats to be played via the AppleTV than is possible when sending the files directly.

## Status
This is very much a first version. It plays video files via an AppleTV 3 and an earlier prototype did the same on an older AppleTV 2 (which I no longer have easy access to).

The http module is a work in progress that does enough for the AppleTV and a little more. It may see more development depending on how my time go and it's use in some of my other projects. It's bundled here to reduce dependency issues.

The tests provide only a basic coverage, but are useful.

As always, feedback is welcome and contributions doubly so!

## Todo
* I really need to add logging support to see what's going on when it doesn't work as expected.
* The progress bar doesn't work as it should under Python3.

## Notes
* For HLS support this module requires a recent build of ffmpeg.
* No cookie support as the AppleTV doesn't need it

## Future Plans
This was written for my own use, but there are a few things I have considered for the future. If anyone else finds this useful, that may help with my time planning :-)

* Improve the code :-)
* Add ChromeCast support
