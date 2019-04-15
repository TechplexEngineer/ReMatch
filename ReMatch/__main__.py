import twitch
import youtube_dl
import tbapi
import time as libtime
import subprocess
import os

twitch_client_id = 'a57grsx9fi8ripztxn8zbxhnvek4cp'
twitch_client = twitch.TwitchClient(client_id=twitch_client_id)


def get_video_info(id):
    vodinf = twitch_client.videos.get_by_id(id)
    created_at = vodinf.get('created_at')
    # print('created at', created_at)
    length_sec = vodinf.get('length')
    print('length', length_sec)
    return {
        'start_time': created_at.timestamp(),
        'length_sec': length_sec,
        'end_time': created_at.timestamp() + length_sec
    }


def download_twitch(id, outfile):
    import os
    exists = os.path.isfile(outfile)
    if exists:
        print("File exists " + outfile)
    else:
        print("Downloading " + outfile)

        vodinf = twitch_client.videos.get_by_id(id)
        ydl_opts = {
            'format': 'best',
            'fixup': 'never',
            'outtmpl': outfile,
            'external_downloader': 'aria2c',           # Note, now depends
            'external-downloader-args': '-c -j 3 -x 3 -s 3 -k 1M'
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([vodinf.get('url')])


tba_apikey = '<TLC Needed>'
# https://github.com/PlasmaRobotics2403/TBApi -- in use
# https://github.com/frc1418/tbapy            -- might be better, more recent
tba_client = tbapi.TBAParser(tba_apikey, cache=False)


def video_contains_match(video, match):
    # print('start  :', video['start_time'])
    # print('actual :', match.actual_time, match.actual_time - video['start_time'])
    # print('end    :', video['end_time'], video['end_time'] - video['start_time'])
    return video['start_time'] < match.actual_time < video['end_time']


def build_video_title(match, event_name, year):
    match_type = match['comp_level']
    match_number = match['match_number']
    set_number = match['set_number']

    if match_type == 'qm':
        match_type = 'Qualification'
    elif match_type == 'qf':
        match_type = 'Quarterfinal'
    elif match_type == 'sf':
        match_type = 'Semifinal'
    elif match_type == 'f':
        match_type = 'Final'
    else:
        print('WARN comp_level {} unknown'.format(match_type))

    if set_number is not None:
        match_type += ' {} match'.format(set_number)
    # 'Qualification 1 - 2019 Aerospace Valley Regional'
    # 'Semifinal 1 match 1 - 2019 Aerospace Valley Regional'
    return '{} {} - {} {}'.format(match_type, match_number, year, event_name)


# https://www.bogotobogo.com/FFMpeg/ffmpeg_seeking_ss_option_cutting_section_video_image.php
def split_match(match, outdir):
    # depending on how often the keyframes are,
    # we might need to have duration be longer
    command = [
        'ffmpeg',
        '-hide_banner',             # Hide the banner
        '-loglevel warning',        # quiet! https://superuser.com/a/438280
        '-y',                       # overwrite existing files
        '-ss {start_offset}',       # Fast Seek (before -i)
        '-i {infile}',              # Input file
        '-t {duration}',            # Duration
        '-threads 3',               # Shouldn't matter
        '-c:v copy -c:a copy',      # Don't re-encode... Let youtube do that
        '-bsf:a aac_adtstoasc',     # Fix weird warning about audio
        '-flags +global_header',    # Fix issue about global header
        '{outdir}/{match_key}.mp4', # Output file
    ]
    command = " ".join(command)
    match['outdir'] = outdir
    command = command.format_map(match)
    print(command)
    subprocess.call(command, shell=True)


if __name__ == '__main__':
    match_length_sec = (2 * 60) + 30
    event_key = '2019marea'
    event_name = 'NE District North Shore Event'
    year = '2019'
    outdir = 'outdir'
    sec_after = 5
    sec_before = 3 * 60  # FIRST rules say results must be posted within 2 mins
                         # post_result_time is not accurate in TBA or FRC

    # Put a list of video IDs here
    videoids = [
        # '399875098', # Junk
        # '399510649', # Junk
        '396909899',
        # '396345600',
        # '396122340',
        # '396113063',
    ]
    videos = []
    for video_id in videoids:
        video = {
            'id': video_id
        }
        video.update(get_video_info(video['id']))
        video['file'] = '{}_{}.mp4'.format(event_key, video['id'])
        videos.append(video)

        download_twitch(video['id'], video['file'])

    to_split = []
    matches = tba_client.get_event_matches(event_key)
    for match in matches:

        # if match.key != '2019marea_qm57':
        #     continue

        # It seems TBA times need timezone correction?
        if libtime.daylight == 0:
            match['actual_time'] = match['actual_time'] + libtime.timezone
            match['post_result_time'] = match['post_result_time'] + \
                libtime.timezone
        else:
            match['actual_time'] = match['actual_time'] + libtime.altzone
            match['post_result_time'] = match['post_result_time'] + \
                libtime.altzone

        # Find which video contains the match
        is_video_found = False
        for video in videos:
            if video_contains_match(video, match):
                print('video {} contains {}'.format(video['file'], match.key))
                is_video_found = True
                start_offset = (match['actual_time'] - video['start_time'])
                start_offset -= sec_before
                result_offset = match['post_result_time'] - video['start_time']
                duration = (result_offset - start_offset) + sec_after
                to_split.append({
                    'infile': video['file'],
                    'match_key': match.key,
                    'video_id': video['id'],
                    'start_offset': start_offset,
                    'duration': duration,
                    # 'end_offset': '',
                    'video_name': build_video_title(match, event_name, year),
                    # 'result_offset': result_offset,
                    'video_id': video['id']
                })
                # print(to_split)
                # import sys
                # sys.exit(1)
                break
        if not is_video_found:
            print('WARN unable to find video for match {}'.format(match.key))

    os.makedirs(outdir, exist_ok=True)

    for match in to_split:
        split_match(match, outdir)
        # @todo upload to youtube in background
